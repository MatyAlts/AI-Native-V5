"""Tests de propagación de `materia_id` end-to-end (ADR-040, Sec 6.2).

Verifica que el tutor-service:
  1. Resuelve `materia_id` desde `comision_id` al abrir el episodio
     (vía `AcademicClient.get_comision`).
  2. Lo cachea en `SessionState` para no re-resolver por turno.
  3. Lo forwardea al `AIGatewayClient.stream()` en cada interacción.
  4. Si la resolución falla (404, exception), degrada a `materia_id=None`
     sin abortar el episodio (BYOK fallback a scope=tenant).

El resolver BYOK del ai-gateway no se ejercita acá — se asume el contrato
del schema `CompleteRequest.materia_id` (ya cubierto en ai-gateway).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import (
    ComisionResponse,
    TareaPracticaResponse,
)
from tutor_service.services.clients import (
    PromptConfig,
    RetrievalResult,
)
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="tutor", hash="a" * 64)


class FakeContentClient:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class CapturingAIGatewayClient:
    """Captura los kwargs de cada `stream()` para verificarlos en assertions."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "tenant_id": tenant_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "materia_id": materia_id,
            }
        )
        # Backlog QA 2026-05-07: nuevo contrato — yieldea dicts.
        yield {"type": "chunk", "content": "respuesta"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> FakeCTRClient:
    return FakeCTRClient()


@pytest.fixture
def fake_ai() -> CapturingAIGatewayClient:
    return CapturingAIGatewayClient()


@pytest.fixture
def academic_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def tutor(redis_client, fake_ctr, fake_ai, academic_mock) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=fake_ai,
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
        academic=academic_mock,
    )


def _published_tp(tenant_id: UUID, comision_id: UUID) -> TareaPracticaResponse:
    now = datetime.now(UTC)
    return TareaPracticaResponse(
        id=uuid4(),
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )


def _comision(tenant_id: UUID, comision_id: UUID, materia_id: UUID) -> ComisionResponse:
    return ComisionResponse(
        id=comision_id,
        tenant_id=tenant_id,
        materia_id=materia_id,
        periodo_id=uuid4(),
    )


# ── Tests ──────────────────────────────────────────────────────────────


async def test_open_episode_resuelve_y_cachea_materia_id(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ai: CapturingAIGatewayClient,
) -> None:
    """Al abrir el episodio, se llama a `get_comision` una vez y el
    materia_id queda en SessionState (verificado vía interact)."""
    tenant_id = uuid4()
    comision_id = uuid4()
    materia_id = uuid4()

    academic_mock.get_tarea_practica.return_value = _published_tp(tenant_id, comision_id)
    academic_mock.get_comision.return_value = _comision(tenant_id, comision_id, materia_id)

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    assert academic_mock.get_comision.await_count == 1
    call = academic_mock.get_comision.await_args
    assert call.kwargs["comision_id"] == comision_id
    assert call.kwargs["tenant_id"] == tenant_id

    # Ahora interact: el materia_id debe llegar al ai-gateway.
    chunks = []
    async for ev in tutor.interact(episode_id, "hola"):
        if ev.get("type") == "chunk":
            chunks.append(ev["content"])
    assert chunks == ["respuesta"]
    assert len(fake_ai.calls) == 1
    assert fake_ai.calls[0]["materia_id"] == materia_id
    assert fake_ai.calls[0]["tenant_id"] == tenant_id


async def test_interact_no_reresuelve_materia_id_por_turno(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ai: CapturingAIGatewayClient,
) -> None:
    """`get_comision` se invoca SOLO en open_episode; los turnos siguientes
    leen el cache de SessionState — esto evita N+1 calls al academic-service."""
    tenant_id = uuid4()
    comision_id = uuid4()
    materia_id = uuid4()

    academic_mock.get_tarea_practica.return_value = _published_tp(tenant_id, comision_id)
    academic_mock.get_comision.return_value = _comision(tenant_id, comision_id, materia_id)

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    # 3 turnos.
    for _ in range(3):
        async for _ev in tutor.interact(episode_id, "msg"):
            pass

    # get_comision NO se invocó por cada interact.
    assert academic_mock.get_comision.await_count == 1
    # Pero el materia_id llegó en cada turno.
    assert len(fake_ai.calls) == 3
    for call in fake_ai.calls:
        assert call["materia_id"] == materia_id


async def test_open_episode_degrada_a_none_si_get_comision_devuelve_404(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ai: CapturingAIGatewayClient,
) -> None:
    """`get_comision` returns None (404) → episode arranca igual con
    materia_id=None. BYOK fallback a scope=tenant en el ai-gateway."""
    tenant_id = uuid4()
    comision_id = uuid4()

    academic_mock.get_tarea_practica.return_value = _published_tp(tenant_id, comision_id)
    academic_mock.get_comision.return_value = None  # comision no encontrada

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    async for _ev in tutor.interact(episode_id, "hola"):
        pass

    assert fake_ai.calls[0]["materia_id"] is None


async def test_open_episode_degrada_a_none_si_get_comision_lanza(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ai: CapturingAIGatewayClient,
) -> None:
    """`get_comision` lanza excepción (5xx, network error) → fail-soft, el
    episodio se abre igual con materia_id=None y se loguea warning."""
    tenant_id = uuid4()
    comision_id = uuid4()

    academic_mock.get_tarea_practica.return_value = _published_tp(tenant_id, comision_id)
    academic_mock.get_comision.side_effect = RuntimeError("connection refused")

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    async for _ev in tutor.interact(episode_id, "hola"):
        pass

    assert fake_ai.calls[0]["materia_id"] is None
