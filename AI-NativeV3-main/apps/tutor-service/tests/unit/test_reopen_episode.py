"""Tests de reopen_episode (reapertura docente, 2026-06-19).

A diferencia de resume_episode (alumno dueño reconstruye su sesión), reopen es
una acción DOCENTE: solo emite `episodio_reabierto` al CTR (el partition_worker
revierte estado closed→open) y NO reconstruye la sesión — eso ocurre cuando el
alumno vuelve a la TP vía su flujo normal de resume.

Cubre:
  - Happy path: docente de la comisión reabre un cerrado → emite
    episodio_reabierto (seq=events_count, hashes del último evento) y devuelve
    estado="open".
  - Authz de pertenencia: docente ajeno a la comisión → 403, sin emitir.
  - Superadmin: reabre sin chequear pertenencia (no llama a academic).
  - Gates: 404 inexistente, 409 si no está cerrado.
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
CLASSIFIER_HASH = "b" * 64


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
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self.episodes.get(str(episode_id))


class _FakeAcademic:
    """Academic fake: list_docentes_comision devuelve user_ids configurables."""

    def __init__(self, docente_user_ids: list[UUID] | None = None) -> None:
        self.docente_user_ids = docente_user_ids or []
        self.list_calls = 0

    async def list_docentes_comision(
        self, comision_id: UUID, tenant_id: UUID, caller_id: UUID
    ) -> list[dict]:
        self.list_calls += 1
        return [{"user_id": str(uid), "rol": "titular"} for uid in self.docente_user_ids]


def _ts(seq: int) -> str:
    return datetime(2026, 6, 19, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _closed_episode(episode_id: UUID, tenant_id: UUID, comision_id: UUID) -> dict:
    """EpisodeWithEvents de un episodio CERRADO (abierto → ... → cerrado)."""
    student_id = uuid4()
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
            "classifier_config_hash": CLASSIFIER_HASH,
        }

    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": "closed",
        "opened_at": _ts(0),
        "closed_at": _ts(3),
        "events_count": 4,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": CLASSIFIER_HASH,
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
                },
            ),
            _event(1, "prompt_enviado", {"content": "hola", "prompt_kind": "exploracion"}),
            _event(2, "tutor_respondio", {"content": "que intentaste?", "model_used": "x"}),
            _event(
                3,
                "episodio_cerrado",
                {"final_chain_hash": "e" * 64, "total_events": 4, "duration_seconds": 60.0},
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


def _make_tutor(redis_client, fake_ctr, academic) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
        academic=academic,
    )


async def test_reopen_happy_path_emite_episodio_reabierto(redis_client, fake_ctr) -> None:
    tenant_id, comision_id, docente_id = uuid4(), uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _closed_episode(episode_id, tenant_id, comision_id)
    academic = _FakeAcademic(docente_user_ids=[docente_id])
    tutor = _make_tutor(redis_client, fake_ctr, academic)

    ctx = await tutor.reopen_episode(
        episode_id=episode_id,
        tenant_id=tenant_id,
        docente_id=docente_id,
        docente_roles=frozenset({"docente"}),
        razon="el alumno pidio seguir",
    )

    assert ctx["estado"] == "open"
    assert ctx["episode_id"] == episode_id
    assert ctx["comision_id"] == comision_id

    # Se emitió exactamente un episodio_reabierto, con seq=events_count y los
    # hashes del último evento de la cadena.
    assert len(fake_ctr.published_events) == 1
    ev = fake_ctr.published_events[0]
    assert ev["event_type"] == "episodio_reabierto"
    assert ev["seq"] == 4  # events_count
    assert ev["payload"]["docente_id"] == str(docente_id)
    assert ev["payload"]["razon"] == "el alumno pidio seguir"
    assert ev["prompt_system_hash"] == PROMPT_HASH
    assert ev["classifier_config_hash"] == CLASSIFIER_HASH


async def test_reopen_docente_ajeno_a_comision_es_403(redis_client, fake_ctr) -> None:
    tenant_id, comision_id = uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _closed_episode(episode_id, tenant_id, comision_id)
    # La comisión tiene OTRO docente; el que pide no pertenece.
    academic = _FakeAcademic(docente_user_ids=[uuid4()])
    tutor = _make_tutor(redis_client, fake_ctr, academic)

    with pytest.raises(HTTPException) as exc:
        await tutor.reopen_episode(
            episode_id=episode_id,
            tenant_id=tenant_id,
            docente_id=uuid4(),  # ajeno
            docente_roles=frozenset({"docente"}),
        )
    assert exc.value.status_code == 403
    assert fake_ctr.published_events == []  # no emitió nada


async def test_reopen_superadmin_no_chequea_pertenencia(redis_client, fake_ctr) -> None:
    tenant_id, comision_id = uuid4(), uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[str(episode_id)] = _closed_episode(episode_id, tenant_id, comision_id)
    academic = _FakeAcademic(docente_user_ids=[])  # nadie asignado
    tutor = _make_tutor(redis_client, fake_ctr, academic)

    ctx = await tutor.reopen_episode(
        episode_id=episode_id,
        tenant_id=tenant_id,
        docente_id=uuid4(),
        docente_roles=frozenset({"superadmin"}),
    )
    assert ctx["estado"] == "open"
    assert academic.list_calls == 0  # bypass: no consultó academic
    assert len(fake_ctr.published_events) == 1


async def test_reopen_episodio_no_cerrado_es_409(redis_client, fake_ctr) -> None:
    tenant_id, comision_id, docente_id = uuid4(), uuid4(), uuid4()
    episode_id = uuid4()
    ep = _closed_episode(episode_id, tenant_id, comision_id)
    ep["estado"] = "open"  # NO cerrado
    fake_ctr.episodes[str(episode_id)] = ep
    academic = _FakeAcademic(docente_user_ids=[docente_id])
    tutor = _make_tutor(redis_client, fake_ctr, academic)

    with pytest.raises(HTTPException) as exc:
        await tutor.reopen_episode(
            episode_id=episode_id,
            tenant_id=tenant_id,
            docente_id=docente_id,
            docente_roles=frozenset({"docente"}),
        )
    assert exc.value.status_code == 409
    assert fake_ctr.published_events == []


async def test_reopen_episodio_inexistente_es_404(redis_client, fake_ctr) -> None:
    tenant_id, docente_id = uuid4(), uuid4()
    tutor = _make_tutor(redis_client, fake_ctr, _FakeAcademic(docente_user_ids=[docente_id]))

    with pytest.raises(HTTPException) as exc:
        await tutor.reopen_episode(
            episode_id=uuid4(),
            tenant_id=tenant_id,
            docente_id=docente_id,
            docente_roles=frozenset({"docente"}),
        )
    assert exc.value.status_code == 404
