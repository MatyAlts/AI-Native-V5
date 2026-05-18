"""Tests del AttestationProducer (ADR-021).

Validan que:
- `publish()` emite XADD al stream correcto con maxlen approximate.
- Los timestamps `+00:00` se normalizan a `Z` antes de emitir.
- Si Redis tira excepcion, `publish()` retorna None sin propagar (fail-soft
  semantics — el cierre del episodio NO debe revertirse por una falla en el
  stream de attestation que ocurre POST-COMMIT).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from ctr_service.services.attestation_producer import (
    ATTESTATION_STREAM,
    ATTESTATION_STREAM_MAXLEN,
    AttestationProducer,
    _normalize_ts,
)


def _payload() -> dict[str, object]:
    return {
        "episode_id": "11111111-2222-3333-4444-555555555555",
        "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "final_chain_hash": "0123456789abcdef" * 4,
        "total_events": 42,
        "ts_episode_closed": "2026-04-27T10:30:00Z",
    }


# ---------------------------------------------------------------------------
# _normalize_ts
# ---------------------------------------------------------------------------


def test_normalize_ts_convierte_offset_a_z() -> None:
    """ISO-8601 con +00:00 se convierte a sufijo Z (formato canonico del piloto)."""
    assert _normalize_ts("2026-04-27T10:30:00+00:00") == "2026-04-27T10:30:00Z"


def test_normalize_ts_preserva_z_existente() -> None:
    """Idempotente para input ya con Z."""
    assert _normalize_ts("2026-04-27T10:30:00Z") == "2026-04-27T10:30:00Z"


def test_normalize_ts_no_toca_otros_offsets() -> None:
    """Solo +00:00 se convierte. Otros offsets se preservan (caso patologico
    pero no queremos corromper datos)."""
    assert _normalize_ts("2026-04-27T10:30:00-03:00") == "2026-04-27T10:30:00-03:00"


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_emite_xadd_al_stream_correcto() -> None:
    redis_mock = AsyncMock()
    redis_mock.xadd.return_value = b"1234567890-0"

    producer = AttestationProducer(redis_client=redis_mock)
    msg_id = await producer.publish(_payload())

    assert msg_id == "1234567890-0"
    redis_mock.xadd.assert_called_once()
    args, kwargs = redis_mock.xadd.call_args
    assert args[0] == ATTESTATION_STREAM  # primer arg = stream name
    assert kwargs["maxlen"] == ATTESTATION_STREAM_MAXLEN
    assert kwargs["approximate"] is True


@pytest.mark.asyncio
async def test_publish_serializa_payload_como_json() -> None:
    redis_mock = AsyncMock()
    redis_mock.xadd.return_value = b"1-0"

    payload = _payload()
    producer = AttestationProducer(redis_client=redis_mock)
    await producer.publish(payload)

    # El segundo arg posicional es el dict de fields {"payload": "<json>"}
    args, _ = redis_mock.xadd.call_args
    fields = args[1]
    decoded = json.loads(fields["payload"])
    assert decoded["episode_id"] == payload["episode_id"]
    assert decoded["final_chain_hash"] == payload["final_chain_hash"]
    assert decoded["total_events"] == 42


@pytest.mark.asyncio
async def test_publish_normaliza_ts_antes_de_emitir() -> None:
    """Si el caller pasa +00:00, el payload emitido al stream tiene Z.
    Critico: el attestation-service espera Z y rechaza otro formato."""
    redis_mock = AsyncMock()
    redis_mock.xadd.return_value = b"1-0"

    payload = {**_payload(), "ts_episode_closed": "2026-04-27T10:30:00+00:00"}
    producer = AttestationProducer(redis_client=redis_mock)
    await producer.publish(payload)

    args, _ = redis_mock.xadd.call_args
    decoded = json.loads(args[1]["payload"])
    assert decoded["ts_episode_closed"] == "2026-04-27T10:30:00Z"


@pytest.mark.asyncio
async def test_publish_retorna_none_si_redis_falla() -> None:
    """Fail-soft: una falla del XADD NO debe propagar al worker. La attestation
    queda perdida (recuperable via reconciliation), pero el cierre del episodio
    YA esta commiteado."""
    redis_mock = AsyncMock()
    redis_mock.xadd.side_effect = ConnectionError("Redis caido")

    producer = AttestationProducer(redis_client=redis_mock)
    result = await producer.publish(_payload())

    assert result is None  # NO levanto excepcion, retorno None


@pytest.mark.asyncio
async def test_publish_retorna_string_aunque_redis_devuelva_bytes() -> None:
    """`redis.asyncio` devuelve bytes por default. El producer normaliza a str."""
    redis_mock = AsyncMock()
    redis_mock.xadd.return_value = b"1234-0"

    producer = AttestationProducer(redis_client=redis_mock)
    result = await producer.publish(_payload())

    assert isinstance(result, str)
    assert result == "1234-0"


@pytest.mark.asyncio
async def test_publish_acepta_stream_custom() -> None:
    """El stream name es configurable (util para tests con stream aislado)."""
    redis_mock = AsyncMock()
    redis_mock.xadd.return_value = b"1-0"

    producer = AttestationProducer(redis_client=redis_mock, stream="test.attestations")
    await producer.publish(_payload())

    args, _ = redis_mock.xadd.call_args
    assert args[0] == "test.attestations"


@pytest.mark.asyncio
async def test_default_stream_y_maxlen_son_los_documentados() -> None:
    """Sanity check de las constantes — si bumpea ATTESTATION_STREAM hay que
    actualizar el ADR y el consumer del attestation-service."""
    assert ATTESTATION_STREAM == "attestation.requests"
    assert ATTESTATION_STREAM_MAXLEN == 100_000
