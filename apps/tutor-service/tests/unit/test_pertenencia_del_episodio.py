"""Un alumno NO puede escribir en la cadena CTR de otro.

El agujero que estos tests fijan: todos los emisores de eventos del
tutor-service recibian `user_id` por parametro y **no lo comparaban con
nada**. Validaban unicamente que existiera la sesion Redis del `episode_id`
recibido, y despues construian el evento desde el `SessionState` de la
VICTIMA (`_build_event(state=state, ...)`). Resultado: el evento se appendeaba
a la cadena del otro alumno, con su `tenant_id` y su `student_pseudonym`, y
con los conteos que eligiera el atacante.

Por que duele mas en `tests_ejecutados`: `test_count_failed == 0` con el
ultimo `tutor_respondio` a >=60s es EXACTAMENTE la regla que el labeler
v1.2.0 traduce a **N4 (apropiacion reflexiva)** — la afirmacion mas fuerte
que la plataforma hace sobre un alumno. Fabricar N4 en la cadena de otro
tira abajo la propiedad que sostiene la tesis.

La asimetria que lo hacia invisible: el 403 "episodio de otro estudiante"
que el docstring de `run-tests` promete SI existia... pero solo cuando la
sesion de la victima estaba vencida, porque lo ponia el `resume_episode`
del heal. Con la sesion VIVA el heal no corre, y la respuesta era 202 con
el evento ya escrito. El docstring documentaba una validacion que el
endpoint hacia en la mitad de los casos.

Cobertura: los 9 emisores HTTP de eventos + `/message` + `/close`. Uno por
endpoint a proposito — el punto no es el evento, es que la clase entera
pasa por `TutorCore.sesion_del_emisor`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

PROMPT_HASH = "abc" + "0" * 61


# ── Dobles ────────────────────────────────────────────────────────────


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="prompt-sistema", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="d" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        yield {"type": "chunk", "content": "respuesta"}


class _FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self.episodes.get(str(episode_id))

    async def find_open_episode(
        self,
        tenant_id: UUID,
        caller_id: UUID,
        student_pseudonym: UUID,
        problema_id: UUID,
        ejercicio_id: UUID | None = None,
    ) -> dict | None:
        return None


def _ts(seq: int) -> str:
    return datetime(2026, 8, 27, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _episodio_persistido(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    *,
    estado: str = "closed",
) -> dict:
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(uuid4()),
        "student_pseudonym": str(student_id),
        "problema_id": str(uuid4()),
        "estado": estado,
        "opened_at": _ts(0),
        "closed_at": _ts(1),
        "events_count": 2,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            {
                "event_uuid": str(uuid4()),
                "episode_id": str(episode_id),
                "seq": 0,
                "event_type": "episodio_abierto",
                "ts": _ts(0),
                "payload": {},
                "prompt_system_hash": PROMPT_HASH,
                "prompt_system_version": "v1.0.0",
                "classifier_config_hash": "b" * 64,
            }
        ],
    }


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> _FakeCTR:
    return _FakeCTR()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


@pytest.fixture
def http(monkeypatch, tutor: TutorCore):
    from tutor_service import main
    from tutor_service.routes import episodes as episodes_module

    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: tutor)
    return TestClient(main.app)


def _headers(user_id: UUID, tenant_id: UUID) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alguien@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }


class _Escenario:
    """Un episodio VIVO de la victima y un atacante con sesion propia."""

    def __init__(self, episode_id: UUID, victima: UUID, tenant_victima: UUID) -> None:
        self.episode_id = episode_id
        self.victima = victima
        self.tenant_victima = tenant_victima
        self.atacante = uuid4()
        self.tenant_atacante = uuid4()

    @property
    def headers_atacante_mismo_tenant(self) -> dict[str, str]:
        return _headers(self.atacante, self.tenant_victima)

    @property
    def headers_atacante_otro_tenant(self) -> dict[str, str]:
        return _headers(self.atacante, self.tenant_atacante)

    @property
    def headers_victima(self) -> dict[str, str]:
        return _headers(self.victima, self.tenant_victima)


@pytest.fixture
async def escenario(tutor: TutorCore, fake_ctr: _FakeCTR) -> _Escenario:
    victima = uuid4()
    tenant = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant,
        comision_id=uuid4(),
        student_pseudonym=victima,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    # El CTR conoce el episodio: sin esto el heal contesta 404 y el test
    # pasaria por el motivo equivocado.
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="open"
    )
    fake_ctr.published_events.clear()  # ignorar el episodio_abierto
    return _Escenario(episode_id, victima, tenant)


# ── Los 9 emisores HTTP de eventos ────────────────────────────────────

# (ruta, body). El `run-tests` va con `failed=0`: es el payload que el
# labeler v1.2.0 lee como N4.
_EMISORES: list[tuple[str, dict[str, Any]]] = [
    (
        "run-tests",
        {
            "test_count_total": 10,
            "test_count_passed": 10,
            "test_count_failed": 0,
            "tests_publicos": 10,
            "tests_hidden": 0,
            "ejecucion_ms": 412,
        },
    ),
    ("events/codigo_ejecutado", {"code": "print(1)", "duration_ms": 12.0}),
    ("events/edicion_codigo", {"snapshot": "x = 1", "diff_chars": 5}),
    ("events/lectura_enunciado", {"duration_seconds": 30.0}),
    ("events/anotacion_creada", {"contenido": "reflexion fabricada"}),
    ("events/pestana_perdida", {"trigger": "blur"}),
    ("events/pestana_recuperada", {"tiempo_fuera_segundos": 4.0}),
    ("events/copia_intentada", {"seleccion_chars": 10}),
    ("events/pega_intentada", {"contenido_longitud": 10, "contenido_preview": "x"}),
]


@pytest.mark.parametrize("ruta,body", _EMISORES, ids=[r for r, _ in _EMISORES])
def test_emisor_ajeno_mismo_tenant_es_403_y_no_escribe(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, ruta: str, body: dict
) -> None:
    """Sesion VIVA de la victima: el caso que el heal NO cubre."""
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.headers_atacante_mismo_tenant,
    )
    assert resp.status_code == 403, (
        f"{ruta} acepto un evento de un alumno que no es el dueno del episodio "
        f"(status {resp.status_code}, body {resp.text[:200]})"
    )
    assert fake_ctr.published_events == [], (
        f"{ruta} appendeo a la cadena de la victima: {fake_ctr.published_events}"
    )


@pytest.mark.parametrize("ruta,body", _EMISORES, ids=[r for r, _ in _EMISORES])
def test_emisor_ajeno_otro_tenant_es_403_y_no_escribe(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, ruta: str, body: dict
) -> None:
    """Cross-tenant: el evento salia con el tenant de la VICTIMA."""
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.headers_atacante_otro_tenant,
    )
    assert resp.status_code == 403, f"{ruta} status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


@pytest.mark.parametrize("ruta,body", _EMISORES, ids=[r for r, _ in _EMISORES])
def test_el_dueno_sigue_pudiendo_emitir(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario, ruta: str, body: dict
) -> None:
    """La otra mitad: sin esto, un 403 a todo el mundo pasaria los de arriba."""
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/{ruta}",
        json=body,
        headers=escenario.headers_victima,
    )
    assert resp.status_code == 202, f"{ruta} le rompio el camino al dueno: {resp.text[:200]}"
    assert len(fake_ctr.published_events) == 1


# ── Los otros dos escritores: /message y /close ───────────────────────


def test_message_ajeno_es_403_y_no_escribe(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario
) -> None:
    """`prompt_enviado` + `tutor_respondio` en la cadena de otro.

    `interact()` ni siquiera recibe `user_id`, asi que la verificacion tiene
    que pasar en la ruta antes de abrir el stream SSE — una vez abierto, el
    error viaja como evento `data:` con status 200 y el cliente no distingue.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/message",
        json={"content": "hola"},
        headers=escenario.headers_atacante_mismo_tenant,
    )
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


def test_close_ajeno_es_403_y_no_cierra(
    http: TestClient, tutor: TutorCore, fake_ctr: _FakeCTR, escenario: _Escenario
) -> None:
    """Cerrar el episodio de otro alumno: `episodio_cerrado` en su cadena."""
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/close",
        json={"reason": "student_closed"},
        headers=escenario.headers_atacante_mismo_tenant,
    )
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


def test_abandoned_ajeno_es_403_y_no_escribe(
    http: TestClient, fake_ctr: _FakeCTR, escenario: _Escenario
) -> None:
    """`episodio_abandonado` ajeno: ademas de escribir, BORRA la sesion.

    Es el unico de la clase que no solo mete un evento sino que le voltea la
    sesion a la victima — el alumno pierde el hilo de la conversacion en
    medio del ejercicio.
    """
    resp = http.post(
        f"/api/v1/episodes/{escenario.episode_id}/abandoned",
        json={"reason": "explicit", "last_activity_seconds_ago": 0.0},
        headers=escenario.headers_atacante_mismo_tenant,
    )
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


def test_reflection_ajena_es_403(http: TestClient, tutor: TutorCore, fake_ctr: _FakeCTR) -> None:
    """`reflexion_completada` post-cierre: validaba tenant, no dueno.

    No pasa por la sesion Redis (ya no existe post-cierre) — lee el episodio
    del CTR. Por eso el chequeo vive ahi y no en `sesion_del_emisor`, pero es
    la misma regla.
    """
    victima = uuid4()
    tenant = uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(
        episode_id, tenant, victima, estado="closed"
    )
    resp = http.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "nada",
            "dificultad_encontrada": "nada",
            "que_haria_distinto": "nada",
            "tiempo_completado_ms": 1000,
        },
        headers=_headers(uuid4(), tenant),  # mismo tenant, otro alumno
    )
    assert resp.status_code == 403, f"status {resp.status_code}: {resp.text[:200]}"
    assert fake_ctr.published_events == []


# ── El service-account sigue pudiendo (workers de abandono/distraccion) ──


async def test_el_service_account_puede_abandonar_por_timeout(
    tutor: TutorCore, fake_ctr: _FakeCTR, escenario: _Escenario
) -> None:
    """ADR-025: `reason="timeout"` lo emite el worker con TUTOR_SERVICE_USER_ID.

    Si la regla de pertenencia lo bloqueara, el `abandonment_worker` dejaria
    de cerrar episodios inactivos y quedarian `open` para siempre.
    """
    seq = await tutor.record_episodio_abandonado(
        episode_id=escenario.episode_id,
        reason="timeout",
        last_activity_seconds_ago=1800.0,
        user_id=TUTOR_SERVICE_USER_ID,
    )
    assert seq is not None
    assert [e["event_type"] for e in fake_ctr.published_events] == ["episodio_abandonado"]


async def test_episodio_inexistente_sigue_devolviendo_None_no_403(
    tutor: TutorCore, escenario: _Escenario
) -> None:
    """Sin sesion no hay dueno que comparar: el contrato viejo (None) manda.

    Importa para el heal: `_emitir_con_heal` distingue "sesion ausente"
    (recuperable) de "episodio ajeno" (definitivo) por el TIPO de la
    excepcion. Si la ausencia empezara a salir como 403, el heal legitimo
    dejaria de correr.
    """
    assert await tutor.sesion_del_emisor(uuid4(), escenario.atacante) is None
