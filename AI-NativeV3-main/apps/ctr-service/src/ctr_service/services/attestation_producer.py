"""Producer del stream `attestation.requests` (ADR-021).

Despues de que un `episodio_cerrado` se persiste exitosamente en Postgres,
el worker emite un XADD a este stream para que el integrity-attestation-service
firme el `final_chain_hash` y appendee al log JSONL externo.

CRITICAL — fail-soft semantics:
- Si Redis esta caido, el XADD falla. NO debe propagarse al caller — el cierre
  del episodio ya esta commiteado a Postgres y NO se debe revertir solo porque
  Redis no responde.
- La attestation queda "pendiente" — un reconciliation job futuro puede
  recuperarla iterando episodios closed sin attestation correspondiente.
- Single stream sin sharding: el orden entre attestations no importa, cada una
  es independiente. El consumer del attestation-service puede procesar en
  paralelo si en algun momento se necesita throughput.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from ctr_service.metrics import (
    ctr_attestations_emitted_total,
    ctr_attestations_pending_count,
)

logger = logging.getLogger(__name__)

# Stream donde se publican attestation requests
ATTESTATION_STREAM = "attestation.requests"

# Cap aproximado del stream para evitar crecimiento descontrolado.
# A 1 attestation por episodio cerrado y ~30 episodios/dia/comision en piloto,
# 100k es ~1 ano de buffer. El consumer del attestation-service consume en
# tiempo real, por lo que el stream raramente acumula.
ATTESTATION_STREAM_MAXLEN = 100_000


def _normalize_ts(ts: str) -> str:
    """Asegura sufijo `Z` en lugar de `+00:00` (formato canonico del piloto)."""
    if ts.endswith("+00:00"):
        return ts[:-6] + "Z"
    return ts


class AttestationProducer:
    """Emite attestation requests al stream `attestation.requests`.

    Uso desde el partition_worker post-commit del `episodio_cerrado`:
        await producer.publish({
            "episode_id": "...",
            "tenant_id": "...",
            "final_chain_hash": "<64-hex>",
            "total_events": <int>,
            "ts_episode_closed": "<ISO-8601-Z>",
        })
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream: str = ATTESTATION_STREAM,
        maxlen: int = ATTESTATION_STREAM_MAXLEN,
    ) -> None:
        self.redis = redis_client
        self.stream = stream
        self.maxlen = maxlen

    async def publish(self, payload: dict[str, Any]) -> str | None:
        """Publica un attestation request. Devuelve el message_id o None si fallo.

        Retorna None en lugar de propagar la excepcion — el caller decide si
        loguear y continuar (politica fail-soft del ADR-021).
        """
        # Normalizacion defensiva del ts (el buffer canonico exige Z, no +00:00)
        if "ts_episode_closed" in payload:
            payload = {**payload, "ts_episode_closed": _normalize_ts(payload["ts_episode_closed"])}

        try:
            msg_id = await self.redis.xadd(
                self.stream,
                {"payload": json.dumps(payload, default=str)},
                maxlen=self.maxlen,
                approximate=True,
            )
            # Métrica: attestation request emitida. El gauge `pending_count`
            # se incrementa acá y se decrementa cuando el integrity-attestation-
            # service confirma firma (call site del consumer, no acá).
            ctr_attestations_emitted_total.add(1)
            ctr_attestations_pending_count.add(1)
            return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
        except Exception as exc:
            logger.warning(
                "attestation_publish_failed stream=%s episode_id=%s error=%s",
                self.stream,
                payload.get("episode_id"),
                exc,
            )
            return None
