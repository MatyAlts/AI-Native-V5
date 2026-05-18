"""Tests del flow ReflexionCompletada (ADR-035, Seccion 10 epic ai-native-completion).

Cubre:
  - record_reflexion_completada emite el evento con seq tomado de events_count
    (DB-backed, NO de la sesion Redis que ya fue borrada en close).
  - El evento se publica con caller_id = student_id (autoria del estudiante,
    no service account del tutor).
  - El payload incluye los 3 campos textuales + prompt_version + tiempo_completado_ms.
  - Episodio no cerrado (estado='open') => ValueError -> 409.
  - Episodio inexistente => ValueError -> 404.
  - Episodio de otro tenant => ValueError -> 404 (defensa en profundidad).
  - Endpoint POST: campos > 500 chars => 422 (validacion Pydantic).
  - Endpoint POST: tiempo_completado_ms negativo => 422.
  - Endpoint POST: happy path => 202 con seq.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import (
    PromptConfig,
    RetrievalResult,
)
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TUTOR_SERVICE_USER_ID, TutorCore

# ── Mocks ────────────────────────────────────────────────────────────


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="x", hash="abc" + "0" * 61)


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
        # Backlog QA 2026-05-07: nuevo contrato — yieldea dicts. Estos tests
        # no ejercitan `interact()`, solo `record_reflexion_completada()`,
        # entonces el generator queda vacio.
        if False:
            yield {"type": "chunk", "content": ""}


class FakeCTRClient:
    """CTR mock con get_episode parametrizable y publish_event acumulador.

    El record_reflexion_completada hace get_episode primero (para extraer
    events_count + hashes), entonces el test puede preconfigurar la respuesta
    sin tener un CTR real corriendo.
    """

    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.captured_callers: list[UUID] = []
        # episodes[episode_id] -> dict con shape EpisodeWithEvents
        self.episodes: dict[UUID, dict[str, Any] | None] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        self.captured_callers.append(caller_id)
        return f"msg-{len(self.published_events)}"

    async def get_episode(
        self, episode_id: UUID, tenant_id: UUID, caller_id: UUID
    ) -> dict | None:
        return self.episodes.get(episode_id)


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> FakeCTRClient:
    return FakeCTRClient()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


def _seed_closed_episode(
    fake_ctr: FakeCTRClient,
    episode_id: UUID,
    tenant_id: UUID,
    events_count: int = 5,
) -> None:
    """Inyecta un episodio cerrado con `events_count` eventos al CTR mock."""
    fake_ctr.episodes[episode_id] = {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(uuid4()),
        "student_pseudonym": str(uuid4()),
        "problema_id": str(uuid4()),
        "estado": "closed",
        "opened_at": "2026-04-01T10:00:00Z",
        "closed_at": "2026-04-01T10:30:00Z",
        "events_count": events_count,
        "last_chain_hash": "f" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": "a" * 64,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            {
                "seq": 0,
                "event_type": "episodio_abierto",
                "prompt_system_version": "v1.0.1",
            }
        ],
    }


# ── Tests del service method ─────────────────────────────────────────


async def test_record_reflexion_completada_publica_con_seq_de_events_count(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """El seq del evento sale de ep.events_count del CTR (NO de la sesion Redis)."""
    tenant_id = uuid4()
    episode_id = uuid4()
    student_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id, events_count=7)

    seq = await tutor.record_reflexion_completada(
        episode_id=episode_id,
        tenant_id=tenant_id,
        user_id=student_id,
        que_aprendiste="aprendi recursion",
        dificultad_encontrada="el caso base",
        que_haria_distinto="dibujarlo en papel primero",
        prompt_version="reflection/v1.0.0",
        tiempo_completado_ms=4200,
    )

    assert seq == 7  # events_count del episodio
    assert len(fake_ctr.published_events) == 1
    ev = fake_ctr.published_events[0]
    assert ev["event_type"] == "reflexion_completada"
    assert ev["seq"] == 7
    assert ev["episode_id"] == str(episode_id)
    assert ev["tenant_id"] == str(tenant_id)
    assert ev["payload"]["que_aprendiste"] == "aprendi recursion"
    assert ev["payload"]["dificultad_encontrada"] == "el caso base"
    assert ev["payload"]["que_haria_distinto"] == "dibujarlo en papel primero"
    assert ev["payload"]["prompt_version"] == "reflection/v1.0.0"
    assert ev["payload"]["tiempo_completado_ms"] == 4200
    # Hashes propagados desde el episodio
    assert ev["prompt_system_hash"] == "a" * 64
    assert ev["classifier_config_hash"] == "b" * 64
    assert ev["prompt_system_version"] == "v1.0.1"


async def test_record_reflexion_completada_caller_es_estudiante_no_service_account(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """La autoria es del estudiante — caller != TUTOR_SERVICE_USER_ID."""
    tenant_id = uuid4()
    episode_id = uuid4()
    student_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id)

    await tutor.record_reflexion_completada(
        episode_id=episode_id,
        tenant_id=tenant_id,
        user_id=student_id,
        que_aprendiste="x",
        dificultad_encontrada="y",
        que_haria_distinto="z",
        prompt_version="reflection/v1.0.0",
        tiempo_completado_ms=1000,
    )

    assert fake_ctr.captured_callers[0] == student_id
    assert fake_ctr.captured_callers[0] != TUTOR_SERVICE_USER_ID


async def test_record_reflexion_completada_episodio_no_cerrado_falla(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """Estado != 'closed' -> ValueError ('no esta cerrado')."""
    tenant_id = uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[episode_id] = {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "estado": "open",
        "events_count": 3,
        "prompt_system_hash": "a" * 64,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [],
    }

    with pytest.raises(ValueError, match="no esta cerrado"):
        await tutor.record_reflexion_completada(
            episode_id=episode_id,
            tenant_id=tenant_id,
            user_id=uuid4(),
            que_aprendiste="x",
            dificultad_encontrada="y",
            que_haria_distinto="z",
            prompt_version="reflection/v1.0.0",
            tiempo_completado_ms=100,
        )


async def test_record_reflexion_completada_episodio_inexistente_falla(
    tutor: TutorCore,
) -> None:
    """get_episode devuelve None -> ValueError ('no encontrado')."""
    with pytest.raises(ValueError, match="no encontrado"):
        await tutor.record_reflexion_completada(
            episode_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            que_aprendiste="x",
            dificultad_encontrada="y",
            que_haria_distinto="z",
            prompt_version="reflection/v1.0.0",
            tiempo_completado_ms=100,
        )


async def test_record_reflexion_completada_otro_tenant_falla(
    tutor: TutorCore, fake_ctr: FakeCTRClient
) -> None:
    """Episodio de otro tenant -> ValueError ('otro tenant'), defensa en profundidad."""
    other_tenant = uuid4()
    requesting_tenant = uuid4()
    episode_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, other_tenant)  # episodio del other_tenant

    with pytest.raises(ValueError, match="otro tenant"):
        await tutor.record_reflexion_completada(
            episode_id=episode_id,
            tenant_id=requesting_tenant,  # tenant distinto al del episodio
            user_id=uuid4(),
            que_aprendiste="x",
            dificultad_encontrada="y",
            que_haria_distinto="z",
            prompt_version="reflection/v1.0.0",
            tiempo_completado_ms=100,
        )


# ── Tests del endpoint HTTP ──────────────────────────────────────────


@pytest.fixture
def http_client(monkeypatch, fake_ctr: FakeCTRClient, redis_client):
    """TestClient con _get_tutor monkeypatched para inyectar el fake."""
    from tutor_service import main
    from tutor_service.routes import episodes as episodes_module

    fake_tutor = TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )
    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: fake_tutor)
    yield TestClient(main.app), fake_tutor


def _student_headers(user_id: UUID, tenant_id: UUID) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@unsl.edu.ar",
        "X-User-Roles": "estudiante",
    }


def test_post_reflection_happy_path_returns_202(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    client, _ = http_client
    tenant_id = uuid4()
    episode_id = uuid4()
    student_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id, events_count=4)

    r = client.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "como pensar el caso base",
            "dificultad_encontrada": "tracking del stack mental",
            "que_haria_distinto": "dibujar arbol de llamadas",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": 5500,
        },
        headers=_student_headers(student_id, tenant_id),
    )

    assert r.status_code == 202
    assert r.json() == {"status": "accepted", "seq": "4"}
    assert len(fake_ctr.published_events) == 1
    assert fake_ctr.published_events[0]["event_type"] == "reflexion_completada"
    assert fake_ctr.captured_callers[0] == student_id


def test_post_reflection_campo_excede_500_chars_returns_422(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    client, _ = http_client
    tenant_id = uuid4()
    episode_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id)

    r = client.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "x" * 501,  # excede max_length=500
            "dificultad_encontrada": "y",
            "que_haria_distinto": "z",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": 100,
        },
        headers=_student_headers(uuid4(), tenant_id),
    )

    assert r.status_code == 422
    # No se publico nada al CTR
    assert len(fake_ctr.published_events) == 0


def test_post_reflection_tiempo_negativo_returns_422(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    client, _ = http_client
    tenant_id = uuid4()
    episode_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id)

    r = client.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "x",
            "dificultad_encontrada": "y",
            "que_haria_distinto": "z",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": -1,
        },
        headers=_student_headers(uuid4(), tenant_id),
    )

    assert r.status_code == 422


def test_post_reflection_episodio_abierto_returns_409(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Episodio en estado 'open' rechaza la reflexion (post-cierre solo)."""
    client, _ = http_client
    tenant_id = uuid4()
    episode_id = uuid4()
    fake_ctr.episodes[episode_id] = {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "estado": "open",  # NO cerrado
        "events_count": 2,
        "prompt_system_hash": "a" * 64,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [],
    }

    r = client.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "x",
            "dificultad_encontrada": "y",
            "que_haria_distinto": "z",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": 100,
        },
        headers=_student_headers(uuid4(), tenant_id),
    )

    assert r.status_code == 409
    assert "no esta cerrado" in r.json()["detail"]


def test_post_reflection_episodio_inexistente_returns_404(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """get_episode = None -> 404."""
    client, _ = http_client

    r = client.post(
        f"/api/v1/episodes/{uuid4()}/reflection",
        json={
            "que_aprendiste": "x",
            "dificultad_encontrada": "y",
            "que_haria_distinto": "z",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": 100,
        },
        headers=_student_headers(uuid4(), uuid4()),
    )

    assert r.status_code == 404


def test_post_reflection_campos_vacios_aceptados_si_validos(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """min_length=0 — strings vacios son validos (alumno puede dejar en blanco)."""
    client, _ = http_client
    tenant_id = uuid4()
    episode_id = uuid4()
    _seed_closed_episode(fake_ctr, episode_id, tenant_id)

    r = client.post(
        f"/api/v1/episodes/{episode_id}/reflection",
        json={
            "que_aprendiste": "",
            "dificultad_encontrada": "",
            "que_haria_distinto": "",
            "prompt_version": "reflection/v1.0.0",
            "tiempo_completado_ms": 100,
        },
        headers=_student_headers(uuid4(), tenant_id),
    )

    assert r.status_code == 202
