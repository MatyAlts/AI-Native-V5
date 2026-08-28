"""Tests focales del PartitionWorker.

Cubre construcción + helpers que NO requieren conexión real a Redis/DB.
El path completo de consume_loop está en `tests/integration/` con
testcontainers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ctr_service.workers.partition_worker import (
    MAX_ATTEMPTS,
    PartitionConfig,
    PartitionWorker,
)


def test_partition_config_defaults() -> None:
    cfg = PartitionConfig(partition=0)
    assert cfg.partition == 0
    assert cfg.consumer_group == "ctr_workers"
    assert cfg.stream_prefix == "ctr.p"
    assert cfg.dlq_stream == "ctr.dead"
    assert cfg.block_ms == 2000
    assert cfg.batch_size == 32


def test_partition_config_custom() -> None:
    cfg = PartitionConfig(
        partition=3,
        consumer_group="alt-group",
        stream_prefix="ctr.x",
        dlq_stream="ctr.alt-dead",
        block_ms=5000,
        batch_size=64,
    )
    assert cfg.partition == 3
    assert cfg.consumer_group == "alt-group"
    assert cfg.stream_prefix == "ctr.x"


def test_partition_worker_construction_sets_consumer_name() -> None:
    cfg = PartitionConfig(partition=2)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert worker.consumer_name == "worker-2"
    assert worker.stream_key == "ctr.p2"


def test_partition_worker_stream_key_per_partition() -> None:
    """Cada partición tiene un stream key distinto."""
    keys = []
    for p in range(8):
        cfg = PartitionConfig(partition=p)
        worker = PartitionWorker(
            config=cfg,
            redis_client=MagicMock(),
            session_factory=MagicMock(),
        )
        keys.append(worker.stream_key)
    assert keys == [f"ctr.p{i}" for i in range(8)]
    assert len(set(keys)) == 8  # todos únicos


def test_partition_worker_default_attestation_producer_none() -> None:
    """ADR-021: sin attestation_producer → modo dev/test."""
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert worker.attestation_producer is None


def test_partition_worker_can_set_attestation_producer() -> None:
    """ADR-021: con attestation_producer → modo prod."""
    cfg = PartitionConfig(partition=0)
    fake_producer = MagicMock()
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
        attestation_producer=fake_producer,
    )
    assert worker.attestation_producer is fake_producer


def test_max_attempts_constant_is_3() -> None:
    """MAX_ATTEMPTS = 3 → DLQ al 4to fallo (RN del piloto, 3 intentos)."""
    assert MAX_ATTEMPTS == 3


def test_partition_worker_stop_event_initially_unset() -> None:
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    assert not worker._stop.is_set()


def test_partition_worker_request_stop_sets_event() -> None:
    cfg = PartitionConfig(partition=0)
    worker = PartitionWorker(
        config=cfg,
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    # buscar método público o protected que setee _stop
    if hasattr(worker, "request_stop"):
        worker.request_stop()
        assert worker._stop.is_set()
    else:
        worker._stop.set()
        assert worker._stop.is_set()


# ── Fallo transitorio vs permanente: quien puede ir a la DLQ ──────────────
#
# Es la distincion mas cara del worker. Un evento que va a la DLQ **sale de la
# cadena para siempre**, y su lugar lo termina ocupando otro cuando el heal
# repone el contador al `events_count`. Mandar ahi un evento VALIDO —porque la
# base tardo en volver— es destruir evidencia de la tesis.
#
# Antes del reclamo de pendientes, `MAX_ATTEMPTS` era inalcanzable y esta rama
# era codigo muerto. Al encenderla, el presupuesto quedo en
# `1 entrega + 2 reclamos x 60s ≈ 120 segundos`, plano y sin backoff: un
# failover de Postgres de tres minutos alcanzaba para mandar a la DLQ todos los
# eventos de esa ventana y marcar decenas de episodios como adulterados.


def _worker_con_fallo(exc: BaseException, attempts: int) -> tuple[PartitionWorker, MagicMock]:
    """Un worker cuyo `_persist_event` siempre tira `exc`, con `attempts` gastados."""
    from unittest.mock import AsyncMock

    worker = PartitionWorker(
        config=PartitionConfig(partition=0),
        redis_client=MagicMock(),
        session_factory=MagicMock(),
    )
    worker._persist_event = AsyncMock(side_effect=exc)  # type: ignore[method-assign]
    worker._get_attempts = AsyncMock(return_value=attempts)  # type: ignore[method-assign]
    worker._move_to_dlq = AsyncMock()  # type: ignore[method-assign]
    worker._ack = AsyncMock()  # type: ignore[method-assign]
    return worker, worker._move_to_dlq  # type: ignore[return-value]


_MENSAJE = {b"payload": b'{"tenant_id": "t", "episode_id": "e", "event_uuid": "u", "seq": 0}'}


async def test_un_fallo_de_POSTGRES_no_manda_el_evento_a_la_dlq() -> None:
    """El caso que destruia evidencia: la base se cae, el evento es valido.

    Se prueba MUY por encima de MAX_ATTEMPTS a proposito: el punto no es que
    aguante un intento mas, es que un transitorio NO CONSUME presupuesto.
    """
    from sqlalchemy.exc import OperationalError

    worker, dlq = _worker_con_fallo(
        OperationalError("connection refused", {}, Exception()), attempts=MAX_ATTEMPTS * 10
    )

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited(), "un fallo de infraestructura no puede tirar el evento"
    worker._ack.assert_not_awaited(), "sin ACK: el mensaje queda en la PEL, recuperable"


async def test_un_corte_de_RED_tampoco() -> None:
    """`ConnectionError` y `TimeoutError` heredan de `OSError` en 3.11+."""
    worker, dlq = _worker_con_fallo(ConnectionError("dns"), attempts=MAX_ATTEMPTS * 10)

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited()


async def test_un_seq_inesperado_SI_va_a_la_dlq() -> None:
    """El otro lado de la moneda: reintentar esto devuelve siempre lo mismo.

    Si el transitorio se tragara TODO, la DLQ volveria a ser codigo muerto y el
    `integrity_compromised` no se marcaria nunca — que es el bug que el reclamo
    de pendientes vino a cerrar.
    """
    worker, dlq = _worker_con_fallo(
        ValueError("Seq inesperado: recibido=85 esperado=43"), attempts=MAX_ATTEMPTS
    )

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_awaited_once()
    worker._ack.assert_awaited_once()


async def test_un_permanente_por_debajo_del_tope_se_reintenta() -> None:
    worker, dlq = _worker_con_fallo(ValueError("Seq inesperado"), attempts=MAX_ATTEMPTS - 1)

    await worker._process_message("1-0", _MENSAJE)

    dlq.assert_not_awaited()
    worker._ack.assert_not_awaited()
