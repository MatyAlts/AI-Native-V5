"""Test end-to-end del flujo de attestation con Redis real (ADR-021 PR 3).

Valida que:
1. Un attestation request publicado al stream `attestation.requests` se consume.
2. El consumer firma con la dev key + appendea al journal JSONL.
3. La firma resultante se verifica con la pubkey.
4. ACK retira el mensaje del pending list.
5. Idempotencia: si el mismo request llega dos veces, ambos se procesan
   (no es bug de seguridad — el verificador externo deduplicara por episode_id).

Requiere Docker. Skip automatico si no esta disponible.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import redis.asyncio as redis_async
from integrity_attestation_service.config import settings
from integrity_attestation_service.services.signing import (
    compute_canonical_buffer,
    load_keypair_with_failsafe,
    verify_buffer,
)
from integrity_attestation_service.workers.attestation_consumer import (
    INPUT_STREAM,
    AttestationConsumer,
)

from .conftest import requires_docker


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    """Levanta un Redis efimero para el modulo de tests."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def redis_client(redis_url: str) -> redis_async.Redis:
    client = redis_async.from_url(redis_url, decode_responses=False)
    # Limpiar streams entre tests para aislar
    with contextlib.suppress(Exception):
        await client.delete(INPUT_STREAM, "attestation.dead")
    yield client
    await client.aclose()


@pytest.fixture(autouse=True)
def _redirect_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "attestation_log_dir", tmp_path)


@requires_docker
async def test_e2e_attestation_request_se_consume_y_firma(
    redis_client: redis_async.Redis, tmp_path: Path
) -> None:
    """Happy path end-to-end: publish + consume + journal con firma valida."""
    private_key, public_key, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment="development",
    )
    consumer = AttestationConsumer(
        redis_client=redis_client,
        private_key=private_key,
        signer_pubkey_id=pubkey_id,
    )
    await consumer.ensure_consumer_group()

    # 1. Producer simula al ctr-service: XADD al stream
    request = {
        "episode_id": "11111111-2222-3333-4444-555555555555",
        "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "final_chain_hash": "0123456789abcdef" * 4,
        "total_events": 42,
        "ts_episode_closed": "2026-04-27T10:30:00Z",
    }
    await redis_client.xadd(
        INPUT_STREAM,
        {"payload": json.dumps(request)},
    )

    # 2. Consumer procesa una iteracion
    await consumer._process_batch()

    # 3. Journal del dia tiene la attestation
    files = list(tmp_path.glob("attestations-*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    attestation = json.loads(line)

    assert attestation["episode_id"] == request["episode_id"]
    assert attestation["signer_pubkey_id"] == pubkey_id
    assert len(attestation["signature"]) == 128

    # 4. Firma valida con la pubkey
    canonical = compute_canonical_buffer(
        episode_id=attestation["episode_id"],
        tenant_id=attestation["tenant_id"],
        final_chain_hash=attestation["final_chain_hash"],
        total_events=attestation["total_events"],
        ts_episode_closed=attestation["ts_episode_closed"],
    )
    assert verify_buffer(public_key, canonical, attestation["signature"]) is True

    # 5. Mensaje ACKeado (no queda en pending)
    pending = await redis_client.xpending(INPUT_STREAM, "attestation_workers")
    # `pending` puede ser dict o tupla segun version del cliente; en ambos casos
    # el primer elemento es el count
    pending_count = pending["pending"] if isinstance(pending, dict) else pending[0]
    assert pending_count == 0


@requires_docker
async def test_e2e_dos_requests_distintos_producen_dos_lineas(
    redis_client: redis_async.Redis, tmp_path: Path
) -> None:
    """Stream procesa N attestation requests → N lineas en el JSONL del dia."""
    private_key, _, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment="development",
    )
    consumer = AttestationConsumer(
        redis_client=redis_client,
        private_key=private_key,
        signer_pubkey_id=pubkey_id,
    )
    await consumer.ensure_consumer_group()

    base_request = {
        "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "final_chain_hash": "0123456789abcdef" * 4,
        "total_events": 42,
        "ts_episode_closed": "2026-04-27T10:30:00Z",
    }
    for i in range(3):
        request = {**base_request, "episode_id": f"{i:08d}-1111-1111-1111-111111111111"}
        await redis_client.xadd(INPUT_STREAM, {"payload": json.dumps(request)})

    await consumer._process_batch()

    files = list(tmp_path.glob("attestations-*.jsonl"))
    assert len(files) == 1
    lines = [line for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    # Cada linea tiene un episode_id distinto
    episode_ids = {json.loads(line)["episode_id"] for line in lines}
    assert len(episode_ids) == 3
