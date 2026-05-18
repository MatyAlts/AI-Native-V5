"""Tests del flow EpisodioAbandonado (ADR-025, G10-A).

Cubre:
  - record_episodio_abandonado emite el evento correcto y borra la sesion.
  - Idempotencia: segunda llamada para el mismo episode_id devuelve None
    sin emitir doble (mitigacion del Riesgo A "emision doble" de audi2.md G10).
  - El worker (_sweep_once) detecta sesiones inactivas y emite con reason="timeout".
  - El worker no toca sesiones activas (last_activity_at reciente).
  - Reasons aceptados (beforeunload / explicit / timeout) se propagan al payload.
  - last_activity_seconds_ago llega tipado float al CTR.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.abandonment_worker import _sweep_once
from tutor_service.services.clients import (
    PromptConfig,
    RetrievalResult,
)
from tutor_service.services.session import SessionManager, SessionState
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="x", hash="abc" + "0" * 61)


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
        # Backlog QA 2026-05-07: nuevo contrato — yieldea dicts.
        if False:
            yield {"type": "chunk", "content": ""}  # generator vacio


class _FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.published_callers: list[UUID] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        self.published_callers.append(caller_id)
        return f"msg-{len(self.published_events)}"


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
def sessions(redis_client) -> SessionManager:
    return SessionManager(redis_client)


# ── record_episodio_abandonado ─────────────────────────────────────────


async def test_record_episodio_abandonado_emite_evento_y_borra_sesion(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    """El happy path: hay sesion → se emite EpisodioAbandonado y se borra el state."""
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.published_events.clear()
    fake_ctr.published_callers.clear()

    seq = await tutor.record_episodio_abandonado(
        episode_id=episode_id,
        reason="beforeunload",
        last_activity_seconds_ago=12.5,
        user_id=student_id,
    )

    assert seq is not None
    assert len(fake_ctr.published_events) == 1
    ev = fake_ctr.published_events[0]
    assert ev["event_type"] == "episodio_abandonado"
    assert ev["seq"] == seq
    assert ev["episode_id"] == str(episode_id)
    assert ev["payload"]["reason"] == "beforeunload"
    # last_activity_seconds_ago debe llegar tipado float al payload.
    assert ev["payload"]["last_activity_seconds_ago"] == pytest.approx(12.5)
    # El caller para reason=beforeunload es el estudiante, no el service-account.
    assert fake_ctr.published_callers[-1] == student_id

    # Idempotencia: la sesion fue borrada
    assert await tutor.sessions.get(episode_id) is None


async def test_record_episodio_abandonado_idempotente_si_no_existe(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    """Mitigacion Riesgo A audi2.md G10: segunda emision para el mismo episodio NO duplica."""
    fake_ctr.published_events.clear()
    # Episodio inexistente — el worker pudo haberlo abandonado antes que llegue beforeunload.
    seq = await tutor.record_episodio_abandonado(
        episode_id=uuid4(),
        reason="beforeunload",
        last_activity_seconds_ago=0.0,
        user_id=uuid4(),
    )
    assert seq is None
    assert len(fake_ctr.published_events) == 0


async def test_record_episodio_abandonado_no_duplica_doble_llamada(
    tutor: TutorCore, fake_ctr: _FakeCTR
) -> None:
    """Doble llamada para el mismo episodio activo: solo la primera emite."""
    tenant_id = uuid4()
    student_id = uuid4()
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.published_events.clear()

    seq1 = await tutor.record_episodio_abandonado(
        episode_id=episode_id,
        reason="beforeunload",
        last_activity_seconds_ago=5.0,
        user_id=student_id,
    )
    seq2 = await tutor.record_episodio_abandonado(
        episode_id=episode_id,
        reason="timeout",
        last_activity_seconds_ago=120.0,
        user_id=TUTOR_SERVICE_USER_ID,
    )
    assert seq1 is not None
    assert seq2 is None
    # Solo se publico el primer evento — no doble emision al CTR.
    abandono_events = [
        e for e in fake_ctr.published_events if e["event_type"] == "episodio_abandonado"
    ]
    assert len(abandono_events) == 1
    assert abandono_events[0]["payload"]["reason"] == "beforeunload"


# ── _sweep_once (worker) ─────────────────────────────────────────────


async def test_sweep_no_toca_sesion_activa(
    tutor: TutorCore, sessions: SessionManager, fake_ctr: _FakeCTR
) -> None:
    """Una sesion con last_activity_at reciente NO debe ser abandonada."""
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.published_events.clear()

    # now ~ ahora, idle_timeout = 30 min; recien abierto NO califica.
    now = time.time()
    abandoned = await _sweep_once(
        sessions=sessions, tutor=tutor, idle_timeout_seconds=30 * 60, now=now
    )

    assert abandoned == 0
    assert len(fake_ctr.published_events) == 0
    # La sesion sigue viva
    assert await sessions.get(episode_id) is not None


async def test_sweep_abandona_sesion_inactiva(
    tutor: TutorCore, sessions: SessionManager, fake_ctr: _FakeCTR
) -> None:
    """Una sesion con last_activity_at antiguo se emite con reason=timeout."""
    episode_id = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.published_events.clear()

    # Forzar un last_activity_at antiguo en el state persistido. Como
    # `set()` lo refresca a now, escribimos directo despues.
    state = await sessions.get(episode_id)
    assert state is not None
    state.last_activity_at = time.time() - 3600  # hace 1 hora
    # set() sobrescribe last_activity_at — para el test inyectamos un now
    # avanzado en el sweep en vez de tocar el state directo.
    sweep_now = time.time() + 3600  # 1 hora en el futuro

    abandoned = await _sweep_once(
        sessions=sessions, tutor=tutor, idle_timeout_seconds=30 * 60, now=sweep_now
    )

    assert abandoned == 1
    assert len(fake_ctr.published_events) == 1
    ev = fake_ctr.published_events[0]
    assert ev["event_type"] == "episodio_abandonado"
    assert ev["payload"]["reason"] == "timeout"
    assert ev["payload"]["last_activity_seconds_ago"] >= 30 * 60
    # La sesion fue borrada del state
    assert await sessions.get(episode_id) is None


async def test_sweep_caller_es_service_account_para_timeout(
    tutor: TutorCore, sessions: SessionManager, fake_ctr: _FakeCTR
) -> None:
    """Para reason=timeout el caller_id debe ser TUTOR_SERVICE_USER_ID (audi2.md G10).

    Distinto de beforeunload/explicit, donde el caller es el UUID del estudiante.
    Esta separacion es relevante para auditoria del CTR — distingue eventos
    iniciados por el usuario vs eventos iniciados por el sistema.
    """
    await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.published_events.clear()
    fake_ctr.published_callers.clear()

    sweep_now = time.time() + 3600
    await _sweep_once(
        sessions=sessions, tutor=tutor, idle_timeout_seconds=30 * 60, now=sweep_now
    )

    assert len(fake_ctr.published_callers) == 1
    assert fake_ctr.published_callers[0] == TUTOR_SERVICE_USER_ID


async def test_sweep_no_emite_si_publish_falla_continua_loop(
    sessions: SessionManager, redis_client, fake_ctr: _FakeCTR
) -> None:
    """Si el publish al CTR falla para una sesion, el sweep continua con la siguiente."""

    class _CTRFails:
        def __init__(self) -> None:
            self.attempts = 0

        async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
            self.attempts += 1
            raise RuntimeError("CTR caido")

    failing_ctr = _CTRFails()
    tutor_failing = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=failing_ctr,  # type: ignore[arg-type]
        sessions=sessions,
    )

    # Abrir 2 episodios — uno fallara al emitir, el sweep debe intentar el segundo.
    state_a = SessionState(
        episode_id=uuid4(),
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        seq=0,
        last_activity_at=time.time() - 3600,
    )
    state_b = SessionState(
        episode_id=uuid4(),
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        seq=0,
        last_activity_at=time.time() - 3600,
    )
    await sessions.set(state_a)
    await sessions.set(state_b)

    sweep_now = time.time() + 3600

    # _sweep_once no debe levantar excepcion aunque publish falle.
    result = await _sweep_once(
        sessions=sessions, tutor=tutor_failing, idle_timeout_seconds=30 * 60, now=sweep_now
    )

    # Ningun abandono "exitoso" registrado, pero el worker no se rompio
    assert result == 0
    # Y intento ambos episodios (no se corto en el primero)
    assert failing_ctr.attempts == 2
