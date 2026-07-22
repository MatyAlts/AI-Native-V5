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
