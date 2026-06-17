"""Idempotencia de open_episode — prevención de episodios fantasma.

Fix 2026-06-17: cuando un alumno reabre un ejercicio que ya tiene un episodio
sin cerrar (estado "open" o "paused"), `open_episode` NO debe crear un episodio
nuevo — debe reanudar el existente. Esto previene la multiplicación de episodios
fantasma que ensucia la trazabilidad criptográfica (CTR) de la tesis.

La red de seguridad real vive en el backend: `open_episode` consulta al CTR
(`find_open_episode`) antes de generar un episode_id nuevo. El frontend hace un
intento best-effort previo, pero el backend es la fuente de verdad y no depende
del timing del worker (que puede tardar en pasar un episodio de "open" a
"paused").

Todas las dependencias están mockeadas con fakes — no toca red.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_HASH = "abc" + "0" * 61


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="prompt-sistema", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(
        self,
        query: str,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
        comision_id: UUID | None = None,
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
        if False:
            yield {"type": "chunk", "content": ""}


class _FakeAcademic:
    """Academic fake mínimo: la TP siempre es válida y permite pausa."""

    def __init__(self, tenant_id: UUID, comision_id: UUID) -> None:
        self._tenant_id = tenant_id
        self._comision_id = comision_id

    async def get_tarea_practica(
        self, tarea_id: UUID, tenant_id: UUID, caller_id: UUID
    ) -> TareaPracticaResponse:
        return TareaPracticaResponse(
            id=tarea_id,
            tenant_id=self._tenant_id,
            comision_id=self._comision_id,
            estado="published",
            fecha_inicio=None,
            fecha_fin=None,
            permite_pausa=True,
        )

    async def get_comision(self, comision_id: UUID, tenant_id: UUID, caller_id: UUID):
        return None  # BYOK degrada a tenant_fallback

    async def get_ejercicio_by_id(self, ejercicio_id: UUID, tenant_id: UUID, caller_id: UUID):
        return None

    async def resolve_ejercicio_orden_in_tp(
        self, tarea_id: UUID, ejercicio_id: UUID, tenant_id: UUID, caller_id: UUID
    ):
        # Orden 1 → no dispara la validación de secuencialidad (orden > 1) y
        # cumple el invariante (ejercicio_id is None) == (ejercicio_orden is None).
        return 1


class _FakeCTR:
    """CTR fake con find_open_episode + get_episode configurables.

    `find_open_episode` busca en `self.episodes` un episodio open|paused que
    matchee (student, problema, ejercicio_id) — mismo contrato que el endpoint
    real `/api/v1/episodes/open-match`. `get_episode` lo usa el resume.
    """

    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}
        self.find_calls = 0

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def find_open_episode(
        self,
        tenant_id: UUID,
        caller_id: UUID,
        student_pseudonym: UUID,
        problema_id: UUID,
        ejercicio_id: UUID | None = None,
    ) -> dict | None:
        self.find_calls += 1
        target = str(ejercicio_id) if ejercicio_id is not None else None
        for ep in self.episodes.values():
            if ep["estado"] not in ("open", "paused"):
                continue
            if str(ep["student_pseudonym"]) != str(student_pseudonym):
                continue
            if str(ep["problema_id"]) != str(problema_id):
                continue
            ep_ejercicio = (ep.get("meta") or {}).get("ejercicio_id")
            if ep_ejercicio == target:
                return {
                    "episode_id": ep["id"],
                    "estado": ep["estado"],
                    "problema_id": ep["problema_id"],
                    "ejercicio_id": ep_ejercicio,
                }
        return None

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self.episodes.get(str(episode_id))


def _ts(seq: int) -> str:
    return datetime(2026, 6, 17, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _existing_episode(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    comision_id: UUID,
    problema_id: UUID,
    *,
    estado: str,
    ejercicio_id: UUID | None,
) -> dict:
    """EpisodeWithEvents de un episodio sin cerrar (open|paused)."""

    def _event(seq: int, event_type: str, payload: dict) -> dict:
        return {
            "event_uuid": str(uuid4()),
            "episode_id": str(episode_id),
            "seq": seq,
            "event_type": event_type,
            "ts": _ts(seq),
            "payload": payload,
            "prompt_system_hash": PROMPT_HASH,
            "prompt_system_version": "v1.0.0",
            "classifier_config_hash": "b" * 64,
        }

    abierto_payload: dict[str, Any] = {
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "comision_id": str(comision_id),
        "curso_config_hash": "c" * 64,
        "model": "claude-haiku-test",
    }
    if ejercicio_id is not None:
        abierto_payload["ejercicio_id"] = str(ejercicio_id)
        abierto_payload["ejercicio_orden"] = 1

    meta = {"ejercicio_id": str(ejercicio_id)} if ejercicio_id is not None else {}

    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": estado,
        "meta": meta,
        "opened_at": _ts(0),
        "closed_at": None,
        "events_count": 3,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            _event(0, "episodio_abierto", abierto_payload),
            _event(1, "prompt_enviado", {"content": "como arranco?", "prompt_kind": "free"}),
            _event(2, "tutor_respondio", {"content": "que sabes del problema?"}),
        ],
    }


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> _FakeCTR:
    return _FakeCTR()


def _make_tutor(redis_client, fake_ctr, tenant_id, comision_id) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
        academic=_FakeAcademic(tenant_id, comision_id),
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )


async def _open(
    tutor: TutorCore,
    tenant_id: UUID,
    comision_id: UUID,
    student_id: UUID,
    problema_id: UUID,
    ejercicio_id: UUID | None = None,
) -> UUID:
    return await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=student_id,
        problema_id=problema_id,
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
        ejercicio_id=ejercicio_id,
    )


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("estado", ["open", "paused"])
async def test_open_episode_reanuda_episodio_sin_cerrar_existente(
    redis_client, fake_ctr: _FakeCTR, estado: str
) -> None:
    """Si ya hay un episodio sin cerrar (open|paused) del mismo
    (alumno, problema, ejercicio), open_episode lo reanuda en vez de crear
    uno nuevo — devuelve el MISMO episode_id y NO emite otro episodio_abierto."""
    tenant_id = uuid4()
    comision_id = uuid4()
    student_id = uuid4()
    problema_id = uuid4()
    ejercicio_id = uuid4()
    existing_id = uuid4()

    fake_ctr.episodes[str(existing_id)] = _existing_episode(
        existing_id,
        tenant_id,
        student_id,
        comision_id,
        problema_id,
        estado=estado,
        ejercicio_id=ejercicio_id,
    )

    tutor = _make_tutor(redis_client, fake_ctr, tenant_id, comision_id)

    returned_id = await _open(
        tutor, tenant_id, comision_id, student_id, problema_id, ejercicio_id
    )

    # Idempotencia: mismo episode_id, sin nuevo episodio_abierto.
    assert returned_id == existing_id
    assert fake_ctr.find_calls == 1
    abiertos = [e for e in fake_ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert abiertos == [], "no debe emitirse un segundo episodio_abierto"

    # La sesión Redis quedó reconstruida (resume) para el episodio existente.
    state = await tutor.sessions.get(existing_id)
    assert state is not None
    assert state.episode_id == existing_id


async def test_open_episode_dos_veces_devuelve_mismo_id(
    redis_client, fake_ctr: _FakeCTR
) -> None:
    """Abrir dos veces el mismo ejercicio devuelve el mismo episode_id.

    La primera apertura crea (no hay match). La segunda matchea el episodio
    "open" que dejó la primera y lo reanuda."""
    tenant_id = uuid4()
    comision_id = uuid4()
    student_id = uuid4()
    problema_id = uuid4()
    ejercicio_id = uuid4()

    tutor = _make_tutor(redis_client, fake_ctr, tenant_id, comision_id)

    first_id = await _open(
        tutor, tenant_id, comision_id, student_id, problema_id, ejercicio_id
    )

    # Simular que el worker persistió el episodio en estado "open" con el
    # ejercicio_id en meta (lo que hace _create_episode en el worker real).
    fake_ctr.episodes[str(first_id)] = _existing_episode(
        first_id,
        tenant_id,
        student_id,
        comision_id,
        problema_id,
        estado="open",
        ejercicio_id=ejercicio_id,
    )

    # Limpiar la sesión Redis para forzar que la 2da apertura pase por resume
    # (simula el caso real donde el alumno reabre desde otra pestaña/sesión).
    await tutor.sessions.delete(first_id)

    second_id = await _open(
        tutor, tenant_id, comision_id, student_id, problema_id, ejercicio_id
    )

    assert second_id == first_id
    # Solo se emitió UN episodio_abierto (el de la primera apertura).
    abiertos = [e for e in fake_ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert len(abiertos) == 1


async def test_open_episode_distinto_ejercicio_no_reanuda(
    redis_client, fake_ctr: _FakeCTR
) -> None:
    """Un episodio abierto de OTRO ejercicio del mismo problema NO se reanuda
    — el match por ejercicio_id debe ser exacto."""
    tenant_id = uuid4()
    comision_id = uuid4()
    student_id = uuid4()
    problema_id = uuid4()
    ejercicio_existente = uuid4()
    ejercicio_nuevo = uuid4()
    existing_id = uuid4()

    fake_ctr.episodes[str(existing_id)] = _existing_episode(
        existing_id,
        tenant_id,
        student_id,
        comision_id,
        problema_id,
        estado="open",
        ejercicio_id=ejercicio_existente,
    )

    tutor = _make_tutor(redis_client, fake_ctr, tenant_id, comision_id)

    returned_id = await _open(
        tutor, tenant_id, comision_id, student_id, problema_id, ejercicio_nuevo
    )

    # No matchea → episodio nuevo con id distinto + nuevo episodio_abierto.
    assert returned_id != existing_id
    abiertos = [e for e in fake_ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert len(abiertos) == 1
    assert abiertos[0]["payload"]["ejercicio_id"] == str(ejercicio_nuevo)


async def test_open_episode_tp_monolitica_reanuda_por_problema(
    redis_client, fake_ctr: _FakeCTR
) -> None:
    """TP monolítica (ejercicio_id=None): el match es por (alumno, problema)
    con meta sin ejercicio_id."""
    tenant_id = uuid4()
    comision_id = uuid4()
    student_id = uuid4()
    problema_id = uuid4()
    existing_id = uuid4()

    fake_ctr.episodes[str(existing_id)] = _existing_episode(
        existing_id,
        tenant_id,
        student_id,
        comision_id,
        problema_id,
        estado="paused",
        ejercicio_id=None,
    )

    tutor = _make_tutor(redis_client, fake_ctr, tenant_id, comision_id)

    returned_id = await _open(tutor, tenant_id, comision_id, student_id, problema_id, None)

    assert returned_id == existing_id
    abiertos = [e for e in fake_ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert abiertos == []
