"""Tests del OveruseDetector (ADR-043, Mejora 5 del plan post-piloto-1).

Cubren los cuatro casos canonicos del plan:
1. Burst por cantidad: 7 prompts en 4 minutos -> match
2. Proportion: 5 prompts y 2 no-prompts en los primeros 10 min -> match
3. No-sobreuso: 5 prompts en 15 minutos -> None
4. Caso limite: exactamente 6 prompts en exactamente 5 minutos -> match

Mas:
5. Episodio sin actividad -> None
6. Solo non-prompts -> None
7. Episodio corto bajo el piso anti-falso-positivo -> None
8. Aislamiento por episode_id (dos episodios paralelos no se contaminan)

Convenciones:
- Usamos un fake Redis async in-memory (no testcontainers) para velocidad.
- Tiempos en epoch float; el test fija `now` y los record llevan offsets.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID, uuid4

import pytest

from tutor_service.services.guardrails import (
    OVERUSE_BURST_THRESHOLD,
    OVERUSE_BURST_WINDOW_SECONDS,
    OVERUSE_MIN_EVENTS_FOR_PROPORTION,
    OVERUSE_PROPORTION_THRESHOLD,
    OVERUSE_PROPORTION_WINDOW_SECONDS,
    OveruseDetector,
)

# ---------------------------------------------------------------------------
# Fake Redis async — implementa el subset que usa OveruseDetector
# ---------------------------------------------------------------------------


class FakeAsyncRedis:
    """Fake Redis async que implementa zadd, zremrangebyscore, zcard,
    zrangebyscore y expire. In-memory por test, sin TTL real (el TTL se
    registra pero no se aplica — los tests son acotados a milisegundos).
    """

    def __init__(self) -> None:
        # key -> {member: score}
        self._zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self._ttls: dict[str, int] = {}

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        before = len(self._zsets[key])
        for member, score in mapping.items():
            self._zsets[key][member] = score
        return len(self._zsets[key]) - before

    async def zremrangebyscore(
        self, key: str, min_score: float, max_score: float
    ) -> int:
        if key not in self._zsets:
            return 0
        to_remove = [
            m for m, s in self._zsets[key].items() if min_score <= s <= max_score
        ]
        for m in to_remove:
            del self._zsets[key][m]
        return len(to_remove)

    async def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    async def zrangebyscore(
        self, key: str, min_score: float, max_score: float
    ) -> list[bytes]:
        if key not in self._zsets:
            return []
        items = [
            (m, s)
            for m, s in self._zsets[key].items()
            if min_score <= s <= max_score
        ]
        items.sort(key=lambda x: x[1])
        return [m.encode() for m, _ in items]

    async def expire(self, key: str, seconds: int) -> bool:
        self._ttls[key] = seconds
        return key in self._zsets


@pytest.fixture
def redis_fake() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
def detector(redis_fake: FakeAsyncRedis) -> OveruseDetector:
    return OveruseDetector(redis_fake)


@pytest.fixture
def episode_id() -> UUID:
    return uuid4()


# ---------------------------------------------------------------------------
# Caso 1: Burst por cantidad — 7 prompts en 4 min => match overuse/burst
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_burst_siete_prompts_en_cuatro_minutos_dispara_overuse(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """7 prompts dentro de la ventana movil de 5 min (300s) supera el
    threshold de 6 prompts -> overuse_burst."""
    now = 1_000_000.0
    # Registrar 6 prompts a lo largo de 4 minutos (240s), antes de `now`
    for i in range(6):
        await detector.record_prompt(episode_id, uuid4(), now - 240 + i * 40)
    # 7mo prompt: el actual (now)
    await detector.record_prompt(episode_id, uuid4(), now)

    match = await detector.check(episode_id, now)
    assert match is not None
    assert match.category == "overuse"
    assert match.severity == 1
    assert "burst" in match.pattern_id
    assert "7 prompts" in match.matched_text


# ---------------------------------------------------------------------------
# Caso 2: Proportion — 5 prompts + 2 non-prompts en los primeros 10 min
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proportion_cinco_prompts_y_dos_non_prompts_dispara_overuse(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """5 prompts + 2 non-prompts en ventana de 600s -> proportion 5/7 = 0.71
    >= 0.7 threshold; total_in_window = 7 >= 5 piso -> overuse_proportion.

    El test debe NO disparar burst (5 prompts en 600s no supera el threshold
    de 6 en 300s)."""
    now = 1_000_000.0
    # 5 prompts distribuidos a lo largo de 10 min (cada 100s)
    for i in range(5):
        await detector.record_prompt(episode_id, uuid4(), now - 500 + i * 100)
    # 2 non-prompts intercalados
    await detector.record_non_prompt_event(episode_id, uuid4(), now - 450)
    await detector.record_non_prompt_event(episode_id, uuid4(), now - 250)

    match = await detector.check(episode_id, now)
    assert match is not None
    assert match.category == "overuse"
    assert "proportion" in match.pattern_id
    assert "5/7" in match.matched_text


# ---------------------------------------------------------------------------
# Caso 3: No-sobreuso — 5 prompts en 15 min => None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cinco_prompts_en_quince_minutos_no_dispara_overuse(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """5 prompts distribuidos en 15 min: ninguno cae en la ventana de 5 min
    juntos (burst falla) y la ventana de proporcion de 10 min solo captura
    los ultimos 4 (proportion = 4/4 = 1.0 pero piso anti-falso-positivo
    requiere >= 5 eventos en la ventana)."""
    now = 1_000_000.0
    # 5 prompts distribuidos en 15 min (cada 225s = 3.75 min)
    for i in range(5):
        await detector.record_prompt(episode_id, uuid4(), now - 900 + i * 225)

    match = await detector.check(episode_id, now)
    assert match is None


# ---------------------------------------------------------------------------
# Caso 4: Limite — exactamente 6 prompts en exactamente 5 minutos => match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limite_seis_prompts_en_exactos_cinco_minutos_dispara_burst(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """Caso limite: 6 prompts dentro de la ventana de 300s exactos.
    El threshold es >= 6 (no estricto) por lo que debe matchear burst."""
    now = 1_000_000.0
    for i in range(6):
        # Distribuidos uniformemente en 5 min: t=0, 60, 120, 180, 240, 300
        await detector.record_prompt(episode_id, uuid4(), now - 300 + i * 60)

    match = await detector.check(episode_id, now)
    assert match is not None
    assert match.category == "overuse"
    assert "burst" in match.pattern_id


# ---------------------------------------------------------------------------
# Caso 5: Sin actividad -> None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sin_actividad_devuelve_none(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """Episodio sin prompts ni non-prompts: el detector no puede gatillar."""
    match = await detector.check(episode_id, 1_000_000.0)
    assert match is None


# ---------------------------------------------------------------------------
# Caso 6: Solo non-prompts -> None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solo_non_prompts_no_dispara_overuse(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """Si el estudiante solo edita codigo y ejecuta tests sin pedirle al
    tutor, no hay overuse (es lo opuesto: trabajo autonomo). El detector
    no debe gatillar."""
    now = 1_000_000.0
    for i in range(10):
        await detector.record_non_prompt_event(episode_id, uuid4(), now - 600 + i * 60)

    match = await detector.check(episode_id, now)
    assert match is None


# ---------------------------------------------------------------------------
# Caso 7: Piso anti-falso-positivo en episodios cortos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_episodio_corto_bajo_el_piso_no_dispara_proportion(
    detector: OveruseDetector, episode_id: UUID
) -> None:
    """Si el episodio tiene menos de OVERUSE_MIN_EVENTS_FOR_PROPORTION (5)
    eventos totales en la ventana, el detector NO gatilla proportion aunque
    todos sean prompts (no es muestra suficiente para inferir patron).

    Caso: 4 prompts en 8 min. Burst falla (necesita 6). Proportion falla
    (4 < 5 piso). Resultado: None.
    """
    now = 1_000_000.0
    for i in range(4):
        await detector.record_prompt(episode_id, uuid4(), now - 480 + i * 120)

    match = await detector.check(episode_id, now)
    assert match is None


# ---------------------------------------------------------------------------
# Caso 8: Aislamiento por episode_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dos_episodios_paralelos_no_se_contaminan(
    detector: OveruseDetector,
) -> None:
    """Si el estudiante A esta en burst y el estudiante B esta tranquilo,
    el detector debe gatillar para A pero no para B. La key Redis incluye
    episode_id por lo que los ledgers son disjuntos."""
    episode_a = uuid4()
    episode_b = uuid4()
    now = 1_000_000.0

    # A: 7 prompts en 4 min (overuse burst)
    for i in range(7):
        await detector.record_prompt(episode_a, uuid4(), now - 240 + i * 40)

    # B: 1 prompt
    await detector.record_prompt(episode_b, uuid4(), now)

    match_a = await detector.check(episode_a, now)
    match_b = await detector.check(episode_b, now)

    assert match_a is not None
    assert match_a.category == "overuse"
    assert match_b is None


# ---------------------------------------------------------------------------
# Anti-regresion: las constantes del modulo siguen siendo las del ADR-043
# ---------------------------------------------------------------------------


def test_constantes_del_adr_043_son_las_documentadas() -> None:
    """Si alguien cambia estas constantes, debe bumpear GUARDRAILS_CORPUS_VERSION
    y actualizar el golden hash + ADR-043 + analisis de sensibilidad."""
    assert OVERUSE_BURST_WINDOW_SECONDS == 300.0
    assert OVERUSE_BURST_THRESHOLD == 6
    assert OVERUSE_PROPORTION_WINDOW_SECONDS == 600.0
    assert OVERUSE_PROPORTION_THRESHOLD == 0.7
    assert OVERUSE_MIN_EVENTS_FOR_PROPORTION == 5
