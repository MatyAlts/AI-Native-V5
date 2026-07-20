"""Tests del worker consumer del stream `attestation.requests` (ADR-021).

Validan el flujo `_sign_and_journal` aislado del Redis: dado un payload
valido, debe firmar + appendear al journal con la attestation completa.
Ademas testea el path de DLQ tras MAX_ATTEMPTS reintentos.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from integrity_attestation_service.config import settings
from integrity_attestation_service.services.signing import (
    DEV_PUBKEY_ID,
    compute_canonical_buffer,
    load_keypair_with_failsafe,
    verify_buffer,
)
from integrity_attestation_service.workers.attestation_consumer import (
    DLQ_STREAM,
    INPUT_STREAM,
    MAX_ATTEMPTS,
    AttestationConsumer,
)

_VALID_REQUEST = {
    "episode_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "final_chain_hash": "0123456789abcdef" * 4,
    "total_events": 42,
    "ts_episode_closed": "2026-04-27T10:30:00Z",
}


@pytest.fixture(autouse=True)
def _redirect_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "attestation_log_dir", tmp_path)


@pytest.fixture
def consumer() -> AttestationConsumer:
    private_key, _public_key, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment="development",
    )
    return AttestationConsumer(
        redis_client=AsyncMock(),
        private_key=private_key,
        signer_pubkey_id=pubkey_id,
    )


# ---------------------------------------------------------------------------
# _sign_and_journal (la parte logica core del worker)
# ---------------------------------------------------------------------------


async def test_sign_and_journal_appendea_archivo_con_firma_valida(
    consumer: AttestationConsumer, tmp_path: Path
) -> None:
    """Happy path: el worker firma + appendea al JSONL, la firma valida con la pubkey."""
    await consumer._sign_and_journal(_VALID_REQUEST)

    # Archivo del dia creado
    files = list(tmp_path.glob("attestations-*.jsonl"))
    assert len(files) == 1

    # Linea contiene episode_id y signature
    content = files[0].read_text(encoding="utf-8")
    assert _VALID_REQUEST["episode_id"] in content
    assert "signature" in content


async def test_sign_and_journal_firma_es_verificable(
    consumer: AttestationConsumer, tmp_path: Path
) -> None:
    """Roundtrip: la firma producida por el worker debe validar con la pubkey."""
    import json

    await consumer._sign_and_journal(_VALID_REQUEST)
    files = list(tmp_path.glob("attestations-*.jsonl"))
    line = files[0].read_text(encoding="utf-8").strip()
    attestation = json.loads(line)

    _, public_key, _ = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment="development",
    )
    canonical = compute_canonical_buffer(
        episode_id=attestation["episode_id"],
        tenant_id=attestation["tenant_id"],
        final_chain_hash=attestation["final_chain_hash"],
        total_events=attestation["total_events"],
        ts_episode_closed=attestation["ts_episode_closed"],
    )
    assert verify_buffer(public_key, canonical, attestation["signature"]) is True


async def test_sign_and_journal_usa_pubkey_id_correcto(
    consumer: AttestationConsumer, tmp_path: Path
) -> None:
    """La attestation lleva el pubkey_id de la dev key (golden test)."""
    import json

    await consumer._sign_and_journal(_VALID_REQUEST)
    line = next(tmp_path.glob("attestations-*.jsonl")).read_text(encoding="utf-8").strip()
    attestation = json.loads(line)
    assert attestation["signer_pubkey_id"] == DEV_PUBKEY_ID


async def test_sign_and_journal_falla_con_request_invalido(
    consumer: AttestationConsumer,
) -> None:
    """Si el request tiene final_chain_hash invalido, el worker raisea
    (eso lo lleva al path de retry/DLQ del _process_message)."""
    bad = {**_VALID_REQUEST, "final_chain_hash": "not-hex"}
    with pytest.raises(ValueError, match="hex"):
        await consumer._sign_and_journal(bad)


async def test_sign_and_journal_falla_con_ts_sin_z(
    consumer: AttestationConsumer,
) -> None:
    """El normalizador del producer del ctr-service ya convierte +00:00 a Z,
    pero si por algun bug llega sin Z, debemos rechazar (no firmar basura)."""
    bad = {**_VALID_REQUEST, "ts_episode_closed": "2026-04-27T10:30:00+00:00"}
    with pytest.raises(ValueError, match="Z"):
        await consumer._sign_and_journal(bad)


# ---------------------------------------------------------------------------
# _process_message: ack en happy path, DLQ tras MAX_ATTEMPTS
# ---------------------------------------------------------------------------


async def test_process_message_acka_en_happy_path(
    consumer: AttestationConsumer, tmp_path: Path
) -> None:
    """Tras procesar exitosamente, el mensaje se XACKea."""
    import json

    fields = {b"payload": json.dumps(_VALID_REQUEST).encode("utf-8")}
    await consumer._process_message("1234-0", fields)

    consumer.redis.xack.assert_awaited_once_with(INPUT_STREAM, "attestation_workers", "1234-0")


async def test_process_message_sin_payload_acka_y_logea(
    consumer: AttestationConsumer,
) -> None:
    """Mensaje malformado (sin field `payload`) se descarta + ackea — no
    queremos atascar el stream con basura no recuperable."""
    fields: dict[bytes, bytes] = {}
    await consumer._process_message("9999-0", fields)
    consumer.redis.xack.assert_awaited_once()


async def test_process_message_va_a_dlq_tras_max_attempts(
    consumer: AttestationConsumer,
) -> None:
    """Tras MAX_ATTEMPTS reintentos fallidos, mover a DLQ + ack."""
    import json

    # Payload invalido fuerza ValueError dentro de _sign_and_journal
    bad = {**_VALID_REQUEST, "final_chain_hash": "not-hex"}
    fields = {b"payload": json.dumps(bad).encode("utf-8")}

    # Mock: xpending_range devuelve >= MAX_ATTEMPTS
    consumer.redis.xpending_range.return_value = [{"times_delivered": MAX_ATTEMPTS}]

    await consumer._process_message("dlq-msg-1", fields)

    # XADD a DLQ
    consumer.redis.xadd.assert_awaited_once()
    dlq_args = consumer.redis.xadd.call_args
    assert dlq_args.args[0] == DLQ_STREAM
    # ACK del mensaje original (para que no se reentregue)
    consumer.redis.xack.assert_awaited_once()


async def test_process_message_no_acka_si_intento_es_recuperable(
    consumer: AttestationConsumer,
) -> None:
    """Si attempts < MAX_ATTEMPTS y hubo fallo, NO se ackea (Redis lo reentrega)."""
    import json

    bad = {**_VALID_REQUEST, "final_chain_hash": "not-hex"}
    fields = {b"payload": json.dumps(bad).encode("utf-8")}
    consumer.redis.xpending_range.return_value = [{"times_delivered": 1}]

    await consumer._process_message("retry-1", fields)

    consumer.redis.xack.assert_not_awaited()
    consumer.redis.xadd.assert_not_awaited()


# ---------------------------------------------------------------------------
# Constantes documentadas en el ADR
# ---------------------------------------------------------------------------


def test_constantes_estan_alineadas_con_adr_021() -> None:
    """Si bumpea estas constantes, hay que actualizar el ADR-021 + el
    AttestationProducer del ctr-service."""
    assert INPUT_STREAM == "attestation.requests"
    assert DLQ_STREAM == "attestation.dead"
    assert MAX_ATTEMPTS == 3
