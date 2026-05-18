"""Tests de apertura de episodio con ejercicio_orden (tp-entregas-correccion).

Verifica que `TutorCore.open_episode` acepta `ejercicio_orden` opcional y
lo incluye en el evento CTR `episodio_abierto`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name,
            version=version,
            content="Eres un tutor.",
            hash="a" * 64,
        )


class FakeContentClient:
    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class FakeAIGatewayClient:
    async def stream(self, **kwargs):
        # Stream nuevo formato (dicts), pero sin contenido para tests que no
        # ejercitan el flujo de interact (solo open/close episode).
        if False:
            yield {"type": "chunk", "content": ""}


def _published_tp(comision_id: UUID, tenant_id: UUID) -> TareaPracticaResponse:
    now = datetime.now(UTC)
    return TareaPracticaResponse(
        id=uuid4(),
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=now - timedelta(hours=1),
        fecha_fin=now + timedelta(hours=1),
    )


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def tutor_with_academic(fake_redis):
    academic = AsyncMock()
    academic.get_comision.return_value = None  # BYOK degrada a tenant
    ctr = MagicMock()
    ctr.publish_event = AsyncMock()

    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=ctr,
        sessions=SessionManager(fake_redis),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    ), academic, ctr


@pytest.mark.asyncio
async def test_open_episode_sin_ejercicio_es_backwards_compatible(
    tutor_with_academic,
) -> None:
    """Sin ejercicio_orden, el flujo es identico al legacy."""
    tutor, academic, ctr = tutor_with_academic
    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)
    academic.get_tarea_practica.return_value = tp

    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tp.id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
    )
    assert episode_id is not None

    # Evento publicado
    assert ctr.publish_event.call_count == 1
    event = ctr.publish_event.call_args[0][0]
    assert event["event_type"] == "episodio_abierto"
    # Sin ejercicio_orden en el payload
    assert "ejercicio_orden" not in event["payload"]


# Tests para `ejercicio_orden` removidos en v1.0 (ADR-041 prep / decisión usuario
# 2026-05-07): la feature `tp-entregas-correccion` con `ejercicio_orden` kwarg en
# TutorCore.open_episode NO entra en v1.0. Si emerge en v1.1+, restituir desde git.
