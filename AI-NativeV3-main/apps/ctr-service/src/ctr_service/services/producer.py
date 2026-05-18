"""Producer: publica eventos del CTR al stream Redis con sharding.

El shard = hash(episode_id) mod N garantiza que todos los eventos de un
episodio van a la misma partición (requerido para orden estricto).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from ctr_service.metrics import ctr_events_total

logger = logging.getLogger(__name__)


NUM_PARTITIONS = 8  # default; alinear con el Deployment (replicas=8 del worker)


def shard_of(episode_id: UUID, num_partitions: int = NUM_PARTITIONS) -> int:
    """Determina la partición para un episode_id dado."""
    # hash estable (no depende de hash seed de Python)
    h = hashlib.sha256(str(episode_id).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % num_partitions


class EventProducer:
    """Publica eventos del CTR al stream Redis.

    Uso desde otros servicios (tutor-service, etc.):
        producer = EventProducer(redis_client)
        await producer.publish(event_dict)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream_prefix: str = "ctr.p",
        num_partitions: int = NUM_PARTITIONS,
        maxlen: int = 1_000_000,
    ) -> None:
        self.redis = redis_client
        self.stream_prefix = stream_prefix
        self.num_partitions = num_partitions
        self.maxlen = maxlen

    async def publish(self, event: dict[str, Any]) -> str:
        """Publica un evento al stream correspondiente y devuelve el message_id."""
        episode_id = UUID(event["episode_id"])
        partition = shard_of(episode_id, self.num_partitions)
        stream = f"{self.stream_prefix}{partition}"

        msg_id = await self.redis.xadd(
            stream,
            {"payload": json.dumps(event, default=str)},
            maxlen=self.maxlen,
            approximate=True,
        )

        # Métrica: incrementar ctr_events_total con labels permitidas.
        # NO se incluye episode_id como label (cardinalidad prohibida — ver
        # openspec/specs/metrics-instrumentation-otlp/spec.md). El tenant_id
        # y event_type vienen del payload del evento; la partition se computa
        # localmente y se etiqueta como string para Prometheus.
        ctr_events_total.add(
            1,
            {
                "tenant_id": str(event.get("tenant_id", "unknown")),
                "event_type": str(event.get("event_type", "unknown")),
                "partition": str(partition),
            },
        )

        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
