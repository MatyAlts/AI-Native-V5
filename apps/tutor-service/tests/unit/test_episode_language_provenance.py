"""multi-language-research-integrity (episode-language-provenance, tasks 2.4-2.6).

El lenguaje del episodio es dato de procedencia para una tesis doctoral: se
resuelve SIEMPRE server-side, desde el `Ejercicio`/`TareaPractica` que
`AcademicClient` ya trae al abrir el episodio (ADR-047/ADR-049 camino banco,
o `get_tarea_practica_full` camino TP monolítica) — nunca del cliente.

Cubre:
  1. Resolución desde el Ejercicio del banco (task 2.4).
  2. Resolución desde la TP monolítica (task 2.4).
  3. Default 'python' cuando no hay contexto pedagógico resuelto (fail-soft,
     academic no configurado o ambas consultas fallaron) — mismo criterio
     que los episodios legacy pre-cambio.
  4. `_resolve_episode_language` unit puro (todas las ramas).
  5. El body del POST /episodes NUNCA influye el `language` resuelto,
     aunque el cliente lo mande explícito (task 2.5).
  6. Reabrir/reanudar un episodio existente NO reescribe el `language` del
     evento `episodio_abierto` original, aunque el ejercicio haya cambiado
     de lenguaje después de abierto (task 2.6).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_HASH = "abc" + "0" * 61


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="Eres un tutor.", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(self, **kwargs) -> AsyncIterator[dict]:
        if False:
            yield {"type": "chunk", "content": ""}


class _FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def find_open_episode(self, **kwargs) -> dict | None:
        return None


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


def _make_tutor(fake_redis, academic=None) -> tuple[TutorCore, _FakeCTR]:
    ctr = _FakeCTR()
    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=ctr,
        sessions=SessionManager(fake_redis),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )
    return tutor, ctr


def _abierto_payload(ctr: _FakeCTR) -> dict:
    abiertos = [e for e in ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert len(abiertos) == 1
    return abiertos[0]["payload"]


# ── 1/2. Resolución server-side desde ambos caminos (task 2.4) ────────────


@pytest.mark.asyncio
async def test_language_resuelto_desde_ejercicio_del_banco(fake_redis) -> None:
    """Camino Ejercicio del banco (ADR-047): `language` llega vía
    `get_ejercicio_by_id` — el mismo dict que ya se usa para armar el
    contexto pedagógico, sin round-trip nuevo."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)
    ejercicio_id = uuid4()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = tp
    academic.get_comision.return_value = None
    academic.get_ejercicio_by_id.return_value = {
        "titulo": "Suma",
        "enunciado_md": "Sumá dos números.",
        "language": "java",
    }
    academic.resolve_ejercicio_orden_in_tp.return_value = 1

    tutor, ctr = _make_tutor(fake_redis, academic)

    await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tp.id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
        ejercicio_id=ejercicio_id,
    )

    assert _abierto_payload(ctr)["language"] == "java"


@pytest.mark.asyncio
async def test_language_resuelto_desde_tp_monolitica(fake_redis) -> None:
    """Camino TP monolítica (sin ejercicio_id): `language` llega vía
    `get_tarea_practica_full`."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = tp
    academic.get_comision.return_value = None
    academic.get_tarea_practica_full.return_value = {
        "id": str(tp.id),
        "titulo": "TP1",
        "enunciado": "Resolvé el problema.",
        "language": "java",
    }

    tutor, ctr = _make_tutor(fake_redis, academic)

    await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tp.id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
        # ejercicio_id omitido → TP monolítica
    )

    academic.get_tarea_practica_full.assert_awaited()
    assert _abierto_payload(ctr)["language"] == "java"


@pytest.mark.asyncio
async def test_language_python_cuando_el_ejercicio_lo_declara(fake_redis) -> None:
    """Camino banco con `language: 'python'` explícito — no solo el default
    implícito. Confirma que la resolución lee el valor real, no asume."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)
    ejercicio_id = uuid4()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = tp
    academic.get_comision.return_value = None
    academic.get_ejercicio_by_id.return_value = {"titulo": "Suma", "language": "python"}
    academic.resolve_ejercicio_orden_in_tp.return_value = 1

    tutor, ctr = _make_tutor(fake_redis, academic)

    await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tp.id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
        ejercicio_id=ejercicio_id,
    )

    assert _abierto_payload(ctr)["language"] == "python"


# ── 3. Fail-soft: sin contexto pedagógico resuelto → 'python' ─────────────


@pytest.mark.asyncio
async def test_language_default_python_sin_academic_configurado(fake_redis) -> None:
    """Sin academic-service configurado (`academic=None`), no hay contexto
    pedagógico posible — el episodio se interpreta como Python, igual que
    los episodios legacy pre-cambio."""
    tutor, ctr = _make_tutor(fake_redis, academic=None)

    await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
    )

    assert _abierto_payload(ctr)["language"] == "python"


@pytest.mark.asyncio
async def test_language_default_python_si_get_tarea_practica_full_falla(fake_redis) -> None:
    """Si `get_tarea_practica_full` falla (fail-soft), el episodio se abre
    igual y el `language` degrada a 'python' — no propaga el error."""
    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = tp
    academic.get_comision.return_value = None
    academic.get_tarea_practica_full.side_effect = RuntimeError("academic caído")

    tutor, ctr = _make_tutor(fake_redis, academic)

    await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=uuid4(),
        problema_id=tp.id,
        curso_config_hash="b" * 64,
        classifier_config_hash="c" * 64,
    )

    assert _abierto_payload(ctr)["language"] == "python"


# ── 4. `_resolve_episode_language` — unit puro de todas las ramas ─────────


@pytest.mark.parametrize(
    "contexto_data,expected",
    [
        (None, "python"),
        ({}, "python"),
        ({"titulo": "x"}, "python"),
        ({"language": "java"}, "java"),
        ({"language": "python"}, "python"),
        ({"language": ""}, "python"),  # string vacío no es un lenguaje válido
        ({"language": None}, "python"),
        ({"language": 123}, "python"),  # tipo inesperado — defensivo, no crashea
    ],
)
def test_resolve_episode_language_unit(contexto_data: dict | None, expected: str) -> None:
    assert TutorCore._resolve_episode_language(contexto_data) == expected


# ── 5. El body del POST ignora cualquier `language` del cliente (task 2.5) ─


def _student_headers(user_id: UUID, tenant_id: UUID) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }


@pytest.fixture
def http_client_con_ejercicio_java(monkeypatch, fake_redis):
    """TestClient con un academic fake cuyo Ejercicio resuelve a 'java',
    para probar que el body del cliente NUNCA gana esa resolución."""
    from tutor_service.routes import episodes as episodes_module

    tenant_id = uuid4()
    comision_id = uuid4()
    tp = _published_tp(comision_id, tenant_id)
    ejercicio_id = uuid4()

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = tp
    academic.get_comision.return_value = None
    academic.get_ejercicio_by_id.return_value = {"titulo": "Suma", "language": "java"}
    academic.resolve_ejercicio_orden_in_tp.return_value = 1

    ctr = _FakeCTR()
    fake_tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=ctr,
        sessions=SessionManager(fake_redis),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )
    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: fake_tutor)

    from tutor_service import main

    yield TestClient(main.app), ctr, tenant_id, comision_id, tp.id, ejercicio_id


def test_open_episode_http_ignora_language_del_body(http_client_con_ejercicio_java) -> None:
    """POST /api/v1/episodes con `language` en el body (que ni siquiera es
    un campo del schema `OpenEpisodeRequest`) es completamente ignorado: el
    `language` emitido al CTR es el resuelto server-side desde el
    Ejercicio ('java'), NUNCA el valor mandado por el cliente."""
    client, ctr, tenant_id, comision_id, problema_id, ejercicio_id = http_client_con_ejercicio_java
    student_id = uuid4()

    response = client.post(
        "/api/v1/episodes",
        json={
            "comision_id": str(comision_id),
            "problema_id": str(problema_id),
            "curso_config_hash": "b" * 64,
            "classifier_config_hash": "c" * 64,
            "ejercicio_id": str(ejercicio_id),
            # El cliente intenta declarar un lenguaje distinto del real.
            "language": "typescript",
        },
        headers=_student_headers(student_id, tenant_id),
    )

    assert response.status_code == 201
    assert _abierto_payload(ctr)["language"] == "java"


def test_open_episode_request_no_declara_language() -> None:
    """Verificación de schema, no solo de comportamiento: `OpenEpisodeRequest`
    no tiene un campo `language` — cualquier valor en el body queda
    descartado por Pydantic (`extra='ignore'` default) antes de llegar a
    `TutorCore.open_episode`."""
    from tutor_service.routes.episodes import OpenEpisodeRequest

    assert "language" not in OpenEpisodeRequest.model_fields

    req = OpenEpisodeRequest.model_validate(
        {
            "comision_id": str(uuid4()),
            "problema_id": str(uuid4()),
            "curso_config_hash": "b" * 64,
            "classifier_config_hash": "c" * 64,
            "language": "cobol",
        }
    )
    assert not hasattr(req, "language")
    assert "language" not in req.model_dump()


# ── 6. Reabrir/reanudar NO reescribe el `language` original (task 2.6) ────


class _FakeCTRConEpisodioExistente:
    """CTR fake con un episodio open|paused pre-existente cuyo
    `episodio_abierto` ya tiene `language` grabado — simula el caso real:
    el alumno reabre la pestaña y `open_episode` reanuda en vez de crear."""

    def __init__(self, existing_episode: dict) -> None:
        self.published_events: list[dict[str, Any]] = []
        self._existing = existing_episode
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
        return {
            "episode_id": self._existing["id"],
            "estado": self._existing["estado"],
            "problema_id": self._existing["problema_id"],
            "ejercicio_id": (self._existing.get("meta") or {}).get("ejercicio_id"),
        }

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self._existing


def _existing_episode_con_language(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    comision_id: UUID,
    problema_id: UUID,
    *,
    language: str,
) -> dict:
    def _ev(seq: int, event_type: str, payload: dict) -> dict:
        return {
            "event_uuid": str(uuid4()),
            "episode_id": str(episode_id),
            "seq": seq,
            "event_type": event_type,
            "ts": datetime(2026, 7, 1, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
            "prompt_system_hash": PROMPT_HASH,
            "prompt_system_version": "v1.0.0",
            "classifier_config_hash": "b" * 64,
        }

    abierto_payload = {
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "comision_id": str(comision_id),
        "curso_config_hash": "c" * 64,
        "model": "claude-sonnet-4-6",
        "language": language,
    }
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": "paused",
        "meta": {},
        "opened_at": _ev(0, "episodio_abierto", abierto_payload)["ts"],
        "closed_at": None,
        "events_count": 1,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [_ev(0, "episodio_abierto", abierto_payload)],
    }


@pytest.mark.asyncio
async def test_reabrir_episodio_no_reescribe_language_original(fake_redis) -> None:
    """El episodio existente quedó abierto con `language='java'`. Aunque
    `get_ejercicio_by_id` ahora resolvería 'python' (drift hipotético post-
    apertura), `open_episode` reanuda el episodio existente y NO emite un
    nuevo `episodio_abierto` — el `language` original nunca se toca."""
    tenant_id = uuid4()
    comision_id = uuid4()
    student_id = uuid4()
    problema_id = uuid4()
    existing_id = uuid4()

    existing = _existing_episode_con_language(
        existing_id, tenant_id, student_id, comision_id, problema_id, language="java"
    )
    ctr = _FakeCTRConEpisodioExistente(existing)

    academic = AsyncMock()
    academic.get_tarea_practica.return_value = TareaPracticaResponse(
        id=problema_id,
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=None,
        fecha_fin=None,
        permite_pausa=True,
    )
    academic.get_comision.return_value = None
    # Drift hipotético: si HOY se resolviera de cero, daría 'python'.
    academic.get_ejercicio_by_id.return_value = None
    academic.get_tarea_practica_full.return_value = {"titulo": "x", "language": "python"}

    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=ctr,
        sessions=SessionManager(fake_redis),
        academic=academic,
        default_prompt_version="v1.0.0",
        default_model="claude-sonnet-4-6",
    )

    returned_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=comision_id,
        student_pseudonym=student_id,
        problema_id=problema_id,
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )

    assert returned_id == existing_id
    # Ningún episodio_abierto nuevo — el original (con language='java') es
    # el único que existe en la cadena.
    abiertos_nuevos = [e for e in ctr.published_events if e["event_type"] == "episodio_abierto"]
    assert abiertos_nuevos == [], "reanudar no debe emitir un episodio_abierto nuevo"

    # El evento histórico persistido conserva su language original intacto.
    original_payload = existing["events"][0]["payload"]
    assert original_payload["language"] == "java"
