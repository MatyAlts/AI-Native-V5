"""Tests de validación de TareaPractica al abrir un episodio.

Verifica que `TutorCore.open_episode` rechaza con el HTTP code correcto
cuando la TP no existe, está en draft, archived, fuera de plazo, de otra
comisión o de otro tenant. Happy path: TP published y en plazo abre el
episodio normalmente.

Todas las llamadas al academic-service están mockeadas con AsyncMock —
no toca red.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import (
    PromptConfig,
    RetrievalResult,
)
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

# ── Fakes mínimos (mismos que test_tutor_core) ────────────────────────


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name,
            version=version,
            content="Eres un tutor.",
            hash="a" * 64,
        )


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


class FakeAIGatewayClient:
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        # Backlog QA 2026-05-07: nuevo contrato — yieldea dicts.
        yield {"type": "chunk", "content": "ok"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> FakeCTRClient:
    return FakeCTRClient()


@pytest.fixture
def academic_mock() -> AsyncMock:
    """AsyncMock del AcademicClient. Cada test setea el return_value."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def tutor(redis_client, fake_ctr, academic_mock) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
        academic=academic_mock,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _make_tp(
    tenant_id: UUID,
    comision_id: UUID,
    *,
    estado: str = "published",
    fecha_inicio: datetime | None = None,
    fecha_fin: datetime | None = None,
) -> TareaPracticaResponse:
    return TareaPracticaResponse(
        id=uuid4(),
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


async def _open(
    tutor: TutorCore,
    tenant_id: UUID,
    comision_id: UUID,
    problema_id: UUID,
) -> UUID:
    return await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=problema_id,
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )


# ── Tests ────────────────────────────────────────────────────────────


async def test_open_episode_tarea_no_existe_404(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    academic_mock.get_tarea_practica.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, uuid4(), uuid4(), uuid4())

    assert exc_info.value.status_code == 404
    assert "no encontrada" in exc_info.value.detail
    # No se publicó ningún evento al CTR
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_draft_falla_409(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    tenant_id = uuid4()
    comision_id = uuid4()
    academic_mock.get_tarea_practica.return_value = _make_tp(tenant_id, comision_id, estado="draft")

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 409
    assert "borrador" in exc_info.value.detail
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_archived_falla_409(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    tenant_id = uuid4()
    comision_id = uuid4()
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tenant_id, comision_id, estado="archived"
    )

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 409
    assert "archivada" in exc_info.value.detail
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_otra_comision_falla_400(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    tenant_id = uuid4()
    request_comision = uuid4()
    tp_comision = uuid4()  # diferente
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tenant_id, tp_comision, estado="published"
    )

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, request_comision, uuid4())

    assert exc_info.value.status_code == 400
    assert "comisión" in exc_info.value.detail
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_antes_de_inicio_falla_403(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    tenant_id = uuid4()
    comision_id = uuid4()
    future = datetime.now(UTC) + timedelta(days=2)
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tenant_id, comision_id, estado="published", fecha_inicio=future
    )

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 403
    assert "no ha comenzado" in exc_info.value.detail
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_post_deadline_falla_403(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    tenant_id = uuid4()
    comision_id = uuid4()
    past = datetime.now(UTC) - timedelta(days=1)
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tenant_id, comision_id, estado="published", fecha_fin=past
    )

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 403
    assert "fuera de plazo" in exc_info.value.detail
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_otra_tenant_falla_403(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    request_tenant = uuid4()
    tp_tenant = uuid4()  # diferente
    comision_id = uuid4()
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tp_tenant, comision_id, estado="published"
    )

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, request_tenant, comision_id, uuid4())

    assert exc_info.value.status_code == 403
    assert "tenant" in exc_info.value.detail.lower()
    assert fake_ctr.published_events == []


async def test_open_episode_tarea_published_y_en_plazo_ok(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    """Happy path: TP published, comision/tenant matchean, dentro del
    plazo → episodio se abre y se publica `episodio_abierto` al CTR."""
    tenant_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()
    now = datetime.now(UTC)
    academic_mock.get_tarea_practica.return_value = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )

    episode_id = await _open(tutor, tenant_id, comision_id, problema_id)

    assert isinstance(episode_id, UUID)
    # Se llamó al academic-service dos veces (validación inicial + recheck
    # antes de persistir el episodio para cerrar la race window)
    assert academic_mock.get_tarea_practica.await_count == 2
    call = academic_mock.get_tarea_practica.await_args
    assert call.kwargs["tarea_id"] == problema_id
    assert call.kwargs["tenant_id"] == tenant_id
    # Se publicó el evento episodio_abierto al CTR
    assert len(fake_ctr.published_events) == 1
    assert fake_ctr.published_events[0]["event_type"] == "episodio_abierto"
    assert fake_ctr.published_events[0]["payload"]["problema_id"] == str(problema_id)


async def test_open_episode_recheck_detecta_archive_durante_creacion(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    """Race: la TP estaba published al validar, pero fue archivada antes
    de persistir el episodio. El recheck debe detectarlo y abortar con
    409 sin emitir el evento `episodio_abierto`."""
    tenant_id = uuid4()
    comision_id = uuid4()
    now = datetime.now(UTC)
    tp_published = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )
    tp_archived = _make_tp(
        tenant_id,
        comision_id,
        estado="archived",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )
    academic_mock.get_tarea_practica.side_effect = [tp_published, tp_archived]

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 409
    assert "archivada" in exc_info.value.detail
    assert academic_mock.get_tarea_practica.await_count == 2
    # El recheck cortó antes del publish_event al CTR
    assert fake_ctr.published_events == []


async def test_open_episode_recheck_detecta_deadline_pasado_durante_creacion(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    """Race: la TP estaba en plazo al validar, pero el deadline pasó
    antes de persistir el episodio. El recheck debe detectarlo y abortar
    con 403."""
    tenant_id = uuid4()
    comision_id = uuid4()
    now = datetime.now(UTC)
    tp_in_window = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )
    tp_deadline_passed = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=2),
        fecha_fin=now - timedelta(seconds=1),
    )
    academic_mock.get_tarea_practica.side_effect = [
        tp_in_window,
        tp_deadline_passed,
    ]

    with pytest.raises(HTTPException) as exc_info:
        await _open(tutor, tenant_id, comision_id, uuid4())

    assert exc_info.value.status_code == 403
    assert "fuera de plazo" in exc_info.value.detail
    assert academic_mock.get_tarea_practica.await_count == 2
    assert fake_ctr.published_events == []


async def test_open_episode_recheck_pasa_si_TP_sigue_valido(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    """Happy path con doble validación: ambas llamadas devuelven la
    misma TP válida → episodio se abre normalmente y el evento
    `episodio_abierto` se publica al CTR."""
    tenant_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()
    now = datetime.now(UTC)
    tp = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )
    academic_mock.get_tarea_practica.side_effect = [tp, tp]

    episode_id = await _open(tutor, tenant_id, comision_id, problema_id)

    assert isinstance(episode_id, UUID)
    assert academic_mock.get_tarea_practica.await_count == 2
    assert len(fake_ctr.published_events) == 1
    assert fake_ctr.published_events[0]["event_type"] == "episodio_abierto"


async def test_open_episode_sin_academic_client_no_valida(
    redis_client,
    fake_ctr: FakeCTRClient,
) -> None:
    """Backwards-compat: si TutorCore se construye sin academic client
    (tests legacy), open_episode no falla por la TP."""
    tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
        academic=None,  # explícito
    )
    episode_id = await _open(tutor, uuid4(), uuid4(), uuid4())
    assert isinstance(episode_id, UUID)
    assert len(fake_ctr.published_events) == 1


async def test_open_episode_succeeds_with_tarea_practica_linked_to_template(
    tutor: TutorCore,
    academic_mock: AsyncMock,
    fake_ctr: FakeCTRClient,
) -> None:
    """ADR-016: TP instanciada desde un `TareaPracticaTemplate` (con
    `template_id != null` y `has_drift=true` a nivel academic-service) no
    rompe las 6 validaciones de `tutor_core._validate_tarea_practica`.

    El tutor solo mira la instancia — el `TareaPracticaResponse` que
    consume ni siquiera expone esos campos, y el `problema_id` del evento
    CTR sigue apuntando al UUID de la instancia. Esto es el invariante
    que ADR-016 preserva deliberadamente: zero-impact en tutor y CTR.
    """
    tenant_id = uuid4()
    comision_id = uuid4()
    problema_id = uuid4()  # id de la INSTANCIA (no del template)
    now = datetime.now(UTC)
    # TP instanciada desde template: el academic-service internamente la
    # tiene con template_id=<uuid> y has_drift=True, pero el tutor
    # consume solo los 6 campos de validación.
    tp_from_template = _make_tp(
        tenant_id,
        comision_id,
        estado="published",
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=7),
    )
    academic_mock.get_tarea_practica.return_value = tp_from_template

    episode_id = await _open(tutor, tenant_id, comision_id, problema_id)

    # Las 6 condiciones pasaron: existe, tenant, comisión, published,
    # fecha_inicio ≤ now, fecha_fin ≥ now → episodio abierto.
    assert isinstance(episode_id, UUID)
    assert academic_mock.get_tarea_practica.await_count == 2
    # El CTR recibe el id de la INSTANCIA (no el del template) —
    # invariante ADR-016 para preservar la cadena criptográfica.
    assert len(fake_ctr.published_events) == 1
    assert fake_ctr.published_events[0]["event_type"] == "episodio_abierto"
    assert fake_ctr.published_events[0]["payload"]["problema_id"] == str(problema_id)
