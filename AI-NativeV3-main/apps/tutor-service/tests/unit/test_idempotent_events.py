"""Idempotencia server-side por Idempotency-Key (fix P-17).

Reproduce el escenario que dejaba episodios `integrity_compromised`:

  1. El ctr-client postea un evento (event_uuid=X) → el servidor asigna seq N,
     avanza el contador de sesión y publica al CTR.
  2. Se PIERDE el ACK (no el request). El servidor ya persistió.
  3. El ctr-client REINTENTA el MISMO evento (event_uuid=X).
  4. ANTES del fix: el servidor asignaba seq N+1 y avanzaba el contador → el
     siguiente evento real llegaba con seq N+2, dejando un hueco que el
     partition_worker no puede cerrar → `ValueError("Seq inesperado")` →
     dead-letter → `integrity_compromised=True` permanente.
  5. CON el fix: el reintento (mismo Idempotency-Key) devuelve el MISMO seq N,
     NO avanza el contador y NO re-publica al CTR. El siguiente evento real
     mantiene seq N+1 y la secuencia queda contigua → el worker no se envenena.

Estos tests corren a nivel ruta (TestClient) con fakeredis, sin worker real;
la aserción clave es que la secuencia de seqs publicados queda contigua (sin
hueco), que es exactamente la condición que el partition_worker exige.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

# ── Mocks mínimos de los clientes externos ────────────────────────────


class FakeGovernanceClient:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name, version=version, content="Eres un tutor socrático.", hash="abc" + "0" * 61
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
        yield {"type": "chunk", "content": "ok"}


class FakeCTRClient:
    def __init__(self) -> None:
        self.published_events: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"fake-msg-id-{len(self.published_events)}"


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
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=FakeGovernanceClient(),
        content=FakeContentClient(),
        ai_gateway=FakeAIGatewayClient(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


@pytest.fixture
def http_client(monkeypatch, fake_ctr: FakeCTRClient, redis_client):
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


def _student_headers(user_id: UUID, tenant_id: UUID, idempotency_key: str | None = None) -> dict:
    headers = {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


# ── Test principal: reproduce y previene el envenenamiento P-17 ────────


async def test_retry_mismo_event_uuid_no_avanza_contador(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Reintento con el mismo Idempotency-Key devuelve el MISMO seq, no avanza
    el contador, no re-publica, y el siguiente evento real conserva la secuencia.
    """
    client, tutor = http_client
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
    # seq=0: episodio_abierto ya publicado. Contador de sesión = 1.
    assert len(fake_ctr.published_events) == 1

    uuid_x = str(uuid4())

    # 1er POST de pestana_perdida con event_uuid=X → asigna seq 1.
    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "visibilitychange"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=uuid_x),
    )
    assert r1.status_code == 202
    assert r1.json()["seq"] == "1"
    assert len(fake_ctr.published_events) == 2  # abierto + pestana

    # 2do POST: MISMO event_uuid=X (reintento por ACK perdido) → mismo seq 1,
    # SIN avanzar el contador y SIN re-publicar al CTR.
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "visibilitychange"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=uuid_x),
    )
    assert r2.status_code == 202
    assert r2.json()["seq"] == "1"  # idempotente: mismo seq que la primera vez
    assert len(fake_ctr.published_events) == 2  # NO se re-publicó

    # 3er POST: evento NUEVO real (edicion_codigo) con otro event_uuid → seq 2,
    # NO seq 3. Sin el fix habría sido seq 3 y el worker se envenenaría.
    r3 = client.post(
        f"/api/v1/episodes/{episode_id}/events/edicion_codigo",
        json={"snapshot": "x = 1", "diff_chars": 5, "language": "python"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    assert r3.status_code == 202
    assert r3.json()["seq"] == "2"
    assert len(fake_ctr.published_events) == 3

    # La secuencia de seqs publicados queda CONTIGUA (0,1,2) — exactamente lo
    # que el partition_worker exige (expected_seq = events_count). Sin hueco =
    # sin ValueError = sin dead-letter = sin integrity_compromised.
    seqs = [ev["seq"] for ev in fake_ctr.published_events]
    assert seqs == [0, 1, 2]


async def test_sin_idempotency_key_comportamiento_legacy(
    http_client, fake_ctr: FakeCTRClient
) -> None:
    """Sin header Idempotency-Key el comportamiento es el previo: cada POST
    avanza el contador (backwards-compat con callers que no lo mandan)."""
    client, tutor = http_client
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

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id),  # sin Idempotency-Key
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id),  # sin Idempotency-Key
    )
    assert r1.json()["seq"] == "1"
    assert r2.json()["seq"] == "2"  # sin dedup, avanza normal
    assert len(fake_ctr.published_events) == 3  # abierto + 2 pestanas


async def test_idempotency_keys_distintos_avanzan(http_client, fake_ctr: FakeCTRClient) -> None:
    """Dos eventos con Idempotency-Key DISTINTO son eventos distintos: ambos
    avanzan el contador (no se confunden con un reintento)."""
    client, tutor = http_client
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

    r1 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    r2 = client.post(
        f"/api/v1/episodes/{episode_id}/events/pestana_perdida",
        json={"trigger": "blur"},
        headers=_student_headers(student_id, tenant_id, idempotency_key=str(uuid4())),
    )
    assert r1.json()["seq"] == "1"
    assert r2.json()["seq"] == "2"
    assert len(fake_ctr.published_events) == 3


# ── Test a nivel SessionManager (unidad del storage de dedup) ──────────


async def test_session_manager_seen_roundtrip(redis_client) -> None:
    """get_seen_seq devuelve None para uuid nuevo; el mismo seq tras mark_seen."""
    mgr = SessionManager(redis_client)
    episode_id = uuid4()
    key = str(uuid4())

    assert await mgr.get_seen_seq(episode_id, key) is None
    await mgr.mark_seen(episode_id, key, 7)
    assert await mgr.get_seen_seq(episode_id, key) == 7
    # Otro uuid sigue siendo nuevo (aislamiento por key dentro del episodio).
    assert await mgr.get_seen_seq(episode_id, str(uuid4())) is None
    # Otro episodio no comparte el registro.
    assert await mgr.get_seen_seq(uuid4(), key) is None
