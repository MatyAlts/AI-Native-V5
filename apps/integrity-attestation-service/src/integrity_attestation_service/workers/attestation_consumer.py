"""Worker consumer del stream `attestation.requests` (ADR-021).

Lee requests del ctr-service, firma con la clave Ed25519 institucional, y
appendea al journal JSONL del dia.

⚠ CRITICAL: SINGLE-CONSUMER REQUERIDO
======================================
Este worker ASUME single-consumer del stream. El journal `journal.py` usa
write con O_APPEND (atomico < 4KB) pero NO file lock explicito. Si se corren
2 replicas concurrentes, se pueden appendear lineas duplicadas en el JSONL
del dia.

DEPLOY: el Helm chart (`infrastructure/helm/integrity-attestation/`) DEBE
configurar `replicas: 1`. Si en el futuro se necesita escalado horizontal,
el rediseno correcto es:
- Agregar `filelock` package para sincronizar appends entre procesos, O
- Particionar por episode_id (mismo patron que ctr-service partition_worker).

Garantias (mismas que partition_worker.py del ctr-service):
- At-least-once delivery: el caller del XADD no garantiza entrega exacta.
- Idempotencia delegada al journal: si un mismo episode_id se attestiza dos
  veces, el journal queda con dos lineas duplicadas. NO es bug de seguridad
  (ambas firmas validan), pero el verificador externo deduplicara por
  episode_id en su tool.
- Retry con backoff: hasta MAX_ATTEMPTS reintentos, despues DLQ.

Ejecucion (paralelo al servicio HTTP, NO comparte proceso):
    python -m integrity_attestation_service.workers.attestation_consumer
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from integrity_attestation_service.config import settings
from integrity_attestation_service.services.journal import (
    Attestation,
    append_attestation,
    now_utc_z,
)
from integrity_attestation_service.services.signing import (
    SCHEMA_VERSION,
    compute_canonical_buffer,
    load_keypair_with_failsafe,
    sign_buffer,
)

logger = logging.getLogger(__name__)

# Stream del que consume — coordinado con AttestationProducer del ctr-service
INPUT_STREAM = "attestation.requests"
DLQ_STREAM = "attestation.dead"
CONSUMER_GROUP = "attestation_workers"
MAX_ATTEMPTS = 3


@dataclass
class ConsumerConfig:
    consumer_name: str = "worker-0"
    block_ms: int = 2000
    batch_size: int = 32


class AttestationConsumer:
    """Consumer del stream `attestation.requests` que firma + appendea al journal."""

    def __init__(
        self,
        redis_client: redis.Redis,
        private_key: Any,
        signer_pubkey_id: str,
        config: ConsumerConfig | None = None,
    ) -> None:
        self.redis = redis_client
        self.private_key = private_key
        self.signer_pubkey_id = signer_pubkey_id
        self.cfg = config or ConsumerConfig()
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Permite terminar gracefully (ej. SIGTERM)."""
        self._stop.set()

    async def ensure_consumer_group(self) -> None:
        """Crea el consumer group si no existe (idempotente)."""
        try:
            await self.redis.xgroup_create(
                name=INPUT_STREAM,
                groupname=CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        """Loop principal del worker."""
        await self.ensure_consumer_group()
        logger.info(
            "AttestationConsumer iniciado stream=%s group=%s consumer=%s pubkey_id=%s",
            INPUT_STREAM,
            CONSUMER_GROUP,
            self.cfg.consumer_name,
            self.signer_pubkey_id,
        )

        while not self._stop.is_set():
            try:
                await self._process_batch()
            except Exception:
                logger.exception("Error procesando batch")
                await asyncio.sleep(1)

        logger.info("AttestationConsumer terminado")

    async def _process_batch(self) -> None:
        messages = await self.redis.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=self.cfg.consumer_name,
            streams={INPUT_STREAM: ">"},
            count=self.cfg.batch_size,
            block=self.cfg.block_ms,
        )
        if not messages:
            return

        for _, entries in messages:
            for message_id, fields in entries:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: str, fields: dict[bytes, bytes]) -> None:
        """Procesa un attestation request: firma + appendea al journal + ACK."""
        try:
            raw = fields.get(b"payload")
            if raw is None:
                logger.error("Mensaje %s sin campo 'payload'", message_id)
                await self._ack(message_id)
                return

            request: dict[str, Any] = json.loads(raw)
            await self._sign_and_journal(request)
            await self._ack(message_id)

        except Exception as exc:
            attempts = await self._get_attempts(message_id)
            if attempts >= MAX_ATTEMPTS:
                logger.error(
                    "Mensaje %s fallo %d veces; moviendo a DLQ",
                    message_id,
                    attempts,
                    exc_info=exc,
                )
                await self._move_to_dlq(message_id, fields, str(exc), attempts)
                await self._ack(message_id)
            else:
                logger.warning(
                    "Mensaje %s fallo intento %d/%d; sera reintentado",
                    message_id,
                    attempts,
                    MAX_ATTEMPTS,
                    exc_info=exc,
                )

    async def _sign_and_journal(self, request: dict[str, Any]) -> None:
        """Construye buffer canonico, firma, appendea al journal del dia."""
        canonical = compute_canonical_buffer(
            episode_id=request["episode_id"],
            tenant_id=request["tenant_id"],
            final_chain_hash=request["final_chain_hash"],
            total_events=int(request["total_events"]),
            ts_episode_closed=request["ts_episode_closed"],
            schema_version=SCHEMA_VERSION,
        )
        signature = sign_buffer(self.private_key, canonical)

        attestation = Attestation(
            episode_id=str(request["episode_id"]),
            tenant_id=str(request["tenant_id"]),
            final_chain_hash=request["final_chain_hash"],
            total_events=int(request["total_events"]),
            ts_episode_closed=request["ts_episode_closed"],
            ts_attested=now_utc_z(),
            signer_pubkey_id=self.signer_pubkey_id,
            signature=signature,
            schema_version=SCHEMA_VERSION,
        )

        path = append_attestation(settings.attestation_log_dir, attestation)
        logger.info(
            "attestation_signed episode_id=%s tenant_id=%s pubkey_id=%s journal=%s",
            attestation.episode_id,
            attestation.tenant_id,
            self.signer_pubkey_id,
            path.name,
        )

    async def _get_attempts(self, message_id: str) -> int:
        try:
            pending = await self.redis.xpending_range(
                INPUT_STREAM,
                CONSUMER_GROUP,
                min=message_id,
                max=message_id,
                count=1,
            )
            if pending:
                return int(pending[0].get("times_delivered", 1))
        except Exception:
            return 1
        return 1

    async def _move_to_dlq(
        self,
        message_id: str,
        fields: dict[bytes, bytes],
        error: str,
        attempts: int,
    ) -> None:
        raw = fields.get(b"payload") or b"{}"
        await self.redis.xadd(
            DLQ_STREAM,
            {
                "original_stream": INPUT_STREAM,
                "original_id": message_id,
                "error": error,
                "attempts": str(attempts),
                "payload": raw,
            },
        )

    async def _ack(self, message_id: str) -> None:
        await self.redis.xack(INPUT_STREAM, CONSUMER_GROUP, message_id)


async def run_consumer() -> None:
    """Entry-point para correr el consumer standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    private_key, _, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment=settings.environment,
    )

    redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    consumer = AttestationConsumer(
        redis_client=redis_client,
        private_key=private_key,
        signer_pubkey_id=pubkey_id,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.stop)

    try:
        await consumer.run()
    finally:
        await redis_client.aclose()


def main() -> None:
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
