"""Tests de resume_episode (ADR-055, fix plataforma 2026-06-10 #2).

Cubre:
  - Happy path: episodio paused → sesión reconstruida (seq=events_count,
    historia conversacional, código, model del episodio) SIN emitir eventos.
  - Continuidad de seq: el primer evento post-resume sale con el seq que el
    partition_worker espera (events_count).
  - Gates: 404 episodio inexistente, 403 estudiante ajeno / tenant ajeno,
    409 episodio cerrado.
  - Heal: episodio "open" sin sesión (TTL Redis vencido) también se reanuda.
  - Idempotencia: sesión viva → no se toca ni se relee el CTR.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_HASH = "abc" + "0" * 61


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="prompt-sistema", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(
        self, query: str, comision_id: UUID, top_k: int, tenant_id: UUID, caller_id: UUID
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
    ) -> AsyncIterator[dict]:
        if False:
            yield {"type": "chunk", "content": ""}


class _FakeCTR:
    """CTR fake con get_episode configurable (forma EpisodeWithEvents)."""

    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}
        self.get_episode_calls = 0

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        self.get_episode_calls += 1
        return self.episodes.get(str(episode_id))


def _ts(seq: int) -> str:
    return datetime(2026, 6, 10, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _paused_episode(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    estado: str = "paused",
) -> dict:
    """EpisodeWithEvents de un episodio con 5 eventos: abierto, prompt,
    respuesta, edición de código y abandono."""
    comision_id = uuid4()
    problema_id = uuid4()

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

    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": estado,
        "opened_at": _ts(0),
        "closed_at": None,
        "events_count": 5,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            _event(
                0,
                "episodio_abierto",
                {
                    "student_pseudonym": str(student_id),
                    "problema_id": str(problema_id),
                    "comision_id": str(comision_id),
                    "curso_config_hash": "c" * 64,
                    "model": "claude-haiku-test",
                },
            ),
            _event(1, "prompt_enviado", {"content": "como hago un while?", "prompt_kind": "free"}),
            _event(2, "tutor_respondio", {"content": "que condicion tendria que cortar?"}),
            _event(3, "edicion_codigo", {"snapshot": "while True:\n    pass", "origin": "typed"}),
            _event(
                4,
                "episodio_abandonado",
                {"reason": "beforeunload", "last_activity_seconds_ago": 0.0},
            ),
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


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


async def test_resume_reconstruye_sesion_sin_emitir_eventos(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    ep = _paused_episode(episode_id, tenant_id, student_id)
    fake_ctr.episodes[str(episode_id)] = ep

    ctx = await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)

    # NO se emitió ningún evento al CTR (ADR-055: reanudación derivable).
    assert fake_ctr.published_events == []

    # Contexto devuelto para navegación del frontend.
    assert ctx["episode_id"] == episode_id
    assert ctx["problema_id"] == UUID(ep["problema_id"])
    assert ctx["ejercicio_id"] is None

    # La sesión quedó reconstruida con el seq que el worker espera.
    state = await tutor.sessions.get(episode_id)
    assert state is not None
    assert state.seq == 5  # events_count del episodio persistido
    assert state.tenant_id == tenant_id
    assert state.student_pseudonym == student_id
    assert state.model == "claude-haiku-test"
    assert state.prompt_system_hash == PROMPT_HASH
    assert state.curso_config_hash == "c" * 64
    assert state.current_code == "while True:\n    pass"

    # Historia: system + user + assistant (el abandono no entra al contexto).
    roles = [m["role"] for m in state.messages]
    assert roles == ["system", "user", "assistant"]
    assert state.messages[1]["content"] == "como hago un while?"


async def test_resume_primer_evento_posterior_usa_seq_esperado(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    """El partition_worker exige seq == events_count: el primer evento luego
    del resume tiene que salir con seq=5 (el abandono fue seq=4)."""
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(episode_id, tenant_id, student_id)

    await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)
    seq = await tutor.emit_codigo_ejecutado(
        episode_id=episode_id,
        user_id=student_id,
        payload={"code": "print(1)", "stdout": "1", "stderr": "", "duration_ms": 3.0},
    )

    assert seq == 5
    assert fake_ctr.published_events[-1]["seq"] == 5
    assert fake_ctr.published_events[-1]["event_type"] == "codigo_ejecutado"


async def test_resume_404_si_episodio_no_existe(tutor: TutorCore) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await tutor.resume_episode(episode_id=uuid4(), tenant_id=uuid4(), user_id=uuid4())
    assert exc_info.value.status_code == 404


async def test_resume_403_si_estudiante_ajeno(tutor: TutorCore, fake_ctr: _FakeCTR) -> None:
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(episode_id, tenant_id, student_id)

    with pytest.raises(HTTPException) as exc_info:
        await tutor.resume_episode(
            episode_id=episode_id,
            tenant_id=tenant_id,
            user_id=uuid4(),  # otro estudiante
        )
    assert exc_info.value.status_code == 403
    assert await tutor.sessions.get(episode_id) is None


async def test_resume_403_si_tenant_ajeno(tutor: TutorCore, fake_ctr: _FakeCTR) -> None:
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(episode_id, tenant_id, student_id)

    other_tenant = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await tutor.resume_episode(
            episode_id=episode_id, tenant_id=other_tenant, user_id=student_id
        )
    assert exc_info.value.status_code == 403


async def test_resume_409_si_episodio_cerrado(tutor: TutorCore, fake_ctr: _FakeCTR) -> None:
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(
        episode_id, tenant_id, student_id, estado="closed"
    )

    with pytest.raises(HTTPException) as exc_info:
        await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)
    assert exc_info.value.status_code == 409
    assert await tutor.sessions.get(episode_id) is None


async def test_resume_heal_de_episodio_open_sin_sesion(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    """Episodio `open` cuya sesión Redis venció por TTL sin abandono: el
    resume lo cura reconstruyendo la sesión (gate documentado en ADR-055)."""
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(
        episode_id, tenant_id, student_id, estado="open"
    )

    await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)
    state = await tutor.sessions.get(episode_id)
    assert state is not None
    assert state.seq == 5


async def test_resume_idempotente_con_sesion_viva(tutor: TutorCore, fake_ctr: _FakeCTR) -> None:
    """Si la sesión ya existe (doble click / dos pestañas), el resume no
    relee el CTR ni resetea el seq."""
    tenant_id, student_id, episode_id = uuid4(), uuid4(), uuid4()
    fake_ctr.episodes[str(episode_id)] = _paused_episode(episode_id, tenant_id, student_id)

    await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)
    calls_after_first = fake_ctr.get_episode_calls
    state_before = await tutor.sessions.get(episode_id)
    assert state_before is not None

    # Avanzar el seq simulando actividad post-resume.
    await tutor.sessions.next_seq(state_before)

    ctx = await tutor.resume_episode(episode_id=episode_id, tenant_id=tenant_id, user_id=student_id)

    assert fake_ctr.get_episode_calls == calls_after_first  # no releyó el CTR
    state_after = await tutor.sessions.get(episode_id)
    assert state_after is not None
    assert state_after.seq == 6  # NO se reseteó al events_count persistido
    assert ctx["episode_id"] == episode_id
