"""Cuando el tutor arranca SIN el enunciado, el log lo dice de forma buscable.

QA 08/10 (#17): el tutor abria con "¿En que ejercicio estas trabajando?". El
prompt tiene un fallback legitimo para eso —si la consulta al servicio academico
falla, arranca sin enunciado y le pregunta al estudiante por el problema—, y
desde afuera no habia forma de distinguir "el modelo ignoro el contexto" de "el
contexto nunca llego": la falla se tragaba con un `logger.warning` cuyo texto
cambiaba de un sitio a otro.

El comportamiento NO cambia (best-effort, el episodio se abre igual y el nivel
sigue siendo warning). Lo que se fija es que todos esos warnings lleven la misma
etiqueta, `CONTEXTO_NO_DISPONIBLE_LOG`, para poder grepear los logs de prod.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import CONTEXTO_NO_DISPONIBLE_LOG, TutorCore

PROMPT_BASE = "Sos un tutor socratico."


def _published_tp_response(
    tarea_id: UUID, comision_id: UUID, tenant_id: UUID
) -> TareaPracticaResponse:
    now = datetime.now(UTC)
    return TareaPracticaResponse(
        id=tarea_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=now - timedelta(hours=1),
        fecha_fin=now + timedelta(hours=1),
        permite_pausa=True,
    )


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content=PROMPT_BASE, hash="a" * 64)


class _FakeContent:
    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(self, **kwargs):
        if False:
            yield {"type": "chunk", "content": ""}


def _tutor(academic) -> TutorCore:
    ctr = MagicMock()
    ctr.publish_event = AsyncMock()
    ctr.find_open_episode = AsyncMock(return_value=None)
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=ctr,
        sessions=SessionManager(fakeredis.aioredis.FakeRedis()),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )


def _academic(tenant_id, comision_id, tarea_id) -> AsyncMock:
    academic = AsyncMock()
    academic.get_tarea_practica.return_value = _published_tp_response(
        tarea_id, comision_id, tenant_id
    )
    academic.get_comision.return_value = None
    return academic


def _warnings_etiquetados(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and CONTEXTO_NO_DISPONIBLE_LOG in r.getMessage()
    ]


def test_la_etiqueta_es_un_literal_estable() -> None:
    """Es lo que se grepea en prod: si alguien la cambia, cambian las busquedas."""
    assert CONTEXTO_NO_DISPONIBLE_LOG == "tutor_contexto_no_disponible"


@pytest.mark.asyncio
async def test_tp_monolitica_sin_contexto_loguea_la_etiqueta(caplog) -> None:
    tenant_id, comision_id, tarea_id = uuid4(), uuid4(), uuid4()
    academic = _academic(tenant_id, comision_id, tarea_id)
    academic.get_tarea_practica_full.side_effect = RuntimeError("academic caido")
    tutor = _tutor(academic)

    with caplog.at_level(logging.WARNING, logger="tutor_service.services.tutor_core"):
        episode_id = await tutor.open_episode(
            tenant_id=tenant_id,
            comision_id=comision_id,
            student_pseudonym=uuid4(),
            problema_id=tarea_id,
            curso_config_hash="b" * 64,
            classifier_config_hash="c" * 64,
        )

    etiquetados = _warnings_etiquetados(caplog)
    assert len(etiquetados) == 1, [r.getMessage() for r in caplog.records]
    assert str(tarea_id) in etiquetados[0].getMessage()
    # El comportamiento no cambia: el episodio se abre con el prompt base solo.
    state = await tutor.sessions.get(episode_id)
    assert state is not None
    assert state.messages[0]["content"] == PROMPT_BASE


@pytest.mark.asyncio
async def test_ejercicio_del_banco_sin_contexto_loguea_la_etiqueta(caplog) -> None:
    tenant_id, comision_id, tarea_id, ejercicio_id = uuid4(), uuid4(), uuid4(), uuid4()
    academic = _academic(tenant_id, comision_id, tarea_id)
    academic.get_ejercicio_by_id.side_effect = RuntimeError("academic caido")
    academic.resolve_ejercicio_orden_in_tp.return_value = 1
    tutor = _tutor(academic)

    with caplog.at_level(logging.WARNING, logger="tutor_service.services.tutor_core"):
        episode_id = await tutor.open_episode(
            tenant_id=tenant_id,
            comision_id=comision_id,
            student_pseudonym=uuid4(),
            problema_id=tarea_id,
            curso_config_hash="b" * 64,
            classifier_config_hash="c" * 64,
            ejercicio_id=ejercicio_id,
        )

    etiquetados = _warnings_etiquetados(caplog)
    assert len(etiquetados) == 1, [r.getMessage() for r in caplog.records]
    assert str(ejercicio_id) in etiquetados[0].getMessage()
    state = await tutor.sessions.get(episode_id)
    assert state is not None
    assert state.messages[0]["content"] == PROMPT_BASE


@pytest.mark.asyncio
async def test_con_contexto_no_hay_warning_etiquetado(caplog) -> None:
    """Triangulacion: la etiqueta no aparece cuando el contexto SI llega."""
    tenant_id, comision_id, tarea_id = uuid4(), uuid4(), uuid4()
    academic = _academic(tenant_id, comision_id, tarea_id)
    academic.get_tarea_practica_full.return_value = {
        "titulo": "Par o impar",
        "enunciado": "Decidi si un numero es par o impar.",
    }
    tutor = _tutor(academic)

    with caplog.at_level(logging.WARNING, logger="tutor_service.services.tutor_core"):
        await tutor.open_episode(
            tenant_id=tenant_id,
            comision_id=comision_id,
            student_pseudonym=uuid4(),
            problema_id=tarea_id,
            curso_config_hash="b" * 64,
            classifier_config_hash="c" * 64,
        )

    assert _warnings_etiquetados(caplog) == []
