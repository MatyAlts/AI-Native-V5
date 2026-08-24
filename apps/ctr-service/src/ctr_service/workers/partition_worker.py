"""Worker del CTR — consume una partición del stream y persiste.

Garantiza:
  1. Single-writer por partición → no hay race conditions sobre episodios.
  2. Orden estricto dentro de un episodio → seq consecutivos.
  3. At-least-once delivery → idempotencia por event_uuid.
  4. Retry con backoff → tres intentos antes de DLQ.
  5. DLQ implica integrity_compromised=true para el episodio afectado.

Ejecución:
    python -m ctr_service.workers.partition_worker --partition 0

En K8s corre como StatefulSet con 8 pods; cada pod toma una partición
por su ordinal (ctr-worker-0 toma p0, ctr-worker-1 toma p1, ...).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import signal
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ctr_service.config import settings
from ctr_service.db.session import get_session_factory, tenant_session
from ctr_service.metrics import (
    ctr_episodes_integrity_compromised_total,
    ctr_worker_xpending_count,
)
from ctr_service.models import DeadLetter, Episode, Event
from ctr_service.models.base import GENESIS_HASH, utc_now
from ctr_service.services.attestation_producer import AttestationProducer
from ctr_service.services.hashing import compute_chain_hash, compute_self_hash

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 3  # después se envía a DLQ

# Sesión Redis del tutor-service. El CTR normalmente no conoce keys de otro
# servicio; la excepción es deliberada y está acotada a un DEL. Cuando un
# evento no puede persistirse, el contador de seq del tutor queda adelantado
# respecto de `events_count` y TODO evento posterior de ese episodio se
# rechaza: el alumno sigue trabajando y nada se guarda. Invalidar la sesión
# fuerza que el próximo acceso pase por `resume_episode`, que ya repone el
# contador desde `events_count` (el heal existe y está testeado; lo único
# que faltaba era dispararlo).
TUTOR_SESSION_KEY_PREFIX = "tutor:session:"

# El stub de redis-py tipa xreadgroup() con un Union que cubre variantes de
# respuesta (dict-shaped) que XREADGROUP nunca produce en la practica; con
# decode_responses=False la forma real es siempre esta lista de tuplas
# (ver redis/typing.py::XReadGroupResponse). El cast documenta la garantia
# real en vez de silenciar el chequeo con type: ignore.
_XReadGroupMessages = list[tuple[str, list[tuple[str, dict[bytes, bytes]]]]]


@dataclass
class PartitionConfig:
    partition: int
    consumer_group: str = "ctr_workers"
    stream_prefix: str = "ctr.p"
    dlq_stream: str = "ctr.dead"
    block_ms: int = 2000
    batch_size: int = 32
    # Idle minimo (ms) que debe acumular un mensaje pendiente para que otro
    # ciclo lo reclame via XAUTOCLAIM. Sin este reclamo, un mensaje que
    # falla queda PENDING para siempre: XREADGROUP con ">" solo entrega
    # mensajes nuevos. Los tests lo bajan a 0 para no esperar.
    claim_min_idle_ms: int = 60_000


class PartitionWorker:
    """Consumer de una partición específica del stream ctr.p{N}."""

    def __init__(
        self,
        config: PartitionConfig,
        redis_client: redis.Redis,
        session_factory: async_sessionmaker[AsyncSession],
        attestation_producer: AttestationProducer | None = None,
    ) -> None:
        self.cfg = config
        self.redis = redis_client
        self.session_factory = session_factory
        # ADR-021: si esta seteado, despues de commit de un `episodio_cerrado`
        # se emite XADD al stream de attestation. None = sin attestation
        # externa (modo dev sin G5 desplegado, tests, etc.).
        self.attestation_producer = attestation_producer
        self.consumer_name = f"worker-{config.partition}"
        self.stream_key = f"{config.stream_prefix}{config.partition}"
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Permite terminar gracefully."""
        self._stop.set()

    async def ensure_consumer_group(self) -> None:
        """Crea el consumer group si no existe (idempotente)."""
        try:
            await self.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.cfg.consumer_group,
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
            "Worker partition=%d stream=%s consumer=%s iniciado",
            self.cfg.partition,
            self.stream_key,
            self.consumer_name,
        )

        # Métrica: poll periódico del XPENDING count para reflejar lag por
        # partición. Background task — no bloquea el process loop.
        xpending_task = asyncio.create_task(self._xpending_metric_loop())

        try:
            while not self._stop.is_set():
                try:
                    await self._process_batch()
                except Exception:
                    logger.exception("Error procesando batch en partition=%d", self.cfg.partition)
                    await asyncio.sleep(1)
        finally:
            xpending_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await xpending_task

        logger.info("Worker partition=%d terminado", self.cfg.partition)

    async def _xpending_metric_loop(self) -> None:
        """Loop background que reporta XPENDING count cada 30s al gauge.

        Métrica: `ctr_worker_xpending_count{partition}`. Refleja cuántos
        mensajes están entregados pero sin ACK (lag del consumer del worker).
        Si crece, hay problemas de procesamiento o el worker está caído.
        """
        partition_label = {"partition": str(self.cfg.partition)}
        last_value = 0
        while not self._stop.is_set():
            try:
                pending = await self.redis.xpending(
                    name=self.stream_key,
                    groupname=self.cfg.consumer_group,
                )
                # xpending() devuelve dict con `pending` key (count total)
                current = int(pending.get("pending", 0)) if pending else 0
                # UpDownCounter — emitimos delta vs last_value para que el
                # gauge refleje el valor absoluto.
                delta = current - last_value
                if delta != 0:
                    ctr_worker_xpending_count.add(delta, partition_label)
                    last_value = current
            except Exception:
                logger.debug("Error en xpending poll para partition=%d", self.cfg.partition)
            await asyncio.sleep(30)

    async def _process_batch(self) -> None:
        """Lee un batch del stream y procesa cada mensaje.

        Antes de pedir mensajes nuevos, reclama los que quedaron pendientes
        de un intento anterior: sin eso el retry con DLQ que documenta este
        modulo no llega a ocurrir nunca.
        """
        await self._reclaim_stale_pending()

        # XREADGROUP con block: espera hasta block_ms si no hay mensajes
        messages = cast(
            _XReadGroupMessages,
            await self.redis.xreadgroup(
                groupname=self.cfg.consumer_group,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=self.cfg.batch_size,
                block=self.cfg.block_ms,
            ),
        )

        if not messages:
            return

        # messages es una lista [(stream_key, [(id, fields), ...]) ...]
        for _, entries in messages:
            for message_id, fields in entries:
                await self._process_message(message_id, fields)

    async def _reclaim_stale_pending(self) -> None:
        """Reclama mensajes pendientes que superaron `claim_min_idle_ms`.

        `_process_batch` lee el stream con ">" y eso entrega unicamente
        mensajes nuevos. Un mensaje que falla no se ackea y queda en la PEL
        del grupo, donde ninguna lectura posterior lo alcanza: sin este
        reclamo `_get_attempts` nunca supera 1, MAX_ATTEMPTS es inalcanzable
        y `_move_to_dlq` — junto con el `integrity_compromised` que marca —
        no llega a ejecutarse. El mensaje se pierde en silencio.

        XAUTOCLAIM reasigna esos mensajes a este consumer e incrementa su
        contador de entregas, que es lo que `_get_attempts` consulta. El
        umbral de idle evita reprocesar en bucle apretado un mensaje que
        acaba de fallar.

        Fail-soft: si el reclamo falla, se registra y el ciclo sigue con los
        mensajes nuevos — un problema reclamando no debe frenar la ingesta.
        """
        cursor: Any = "0-0"
        reclaimed = 0
        try:
            while reclaimed < self.cfg.batch_size:
                result = await self.redis.xautoclaim(
                    name=self.stream_key,
                    groupname=self.cfg.consumer_group,
                    consumername=self.consumer_name,
                    min_idle_time=self.cfg.claim_min_idle_ms,
                    start_id=cursor,
                    count=self.cfg.batch_size,
                )
                cursor, entries = result[0], result[1]
                if not entries:
                    break
                for message_id, fields in entries:
                    await self._process_message(message_id, fields)
                    reclaimed += 1
                if not cursor or cursor in ("0-0", b"0-0"):
                    break
        except Exception:
            logger.exception("Error reclamando pendientes en partition=%d", self.cfg.partition)
            return

        if reclaimed:
            logger.info(
                "Reclamados %d mensajes pendientes en partition=%d",
                reclaimed,
                self.cfg.partition,
            )

    async def _process_message(self, message_id: str, fields: dict[bytes, bytes]) -> None:
        """Procesa un mensaje con retry + DLQ."""
        try:
            raw = fields.get(b"payload") or fields.get(b"event")
            if raw is None:
                logger.error("Mensaje %s sin campo 'payload'", message_id)
                await self._ack(message_id)
                return

            event_data: dict[str, Any] = json.loads(raw)
            attestation_payload = await self._persist_event(event_data)
            await self._ack(message_id)

            # ADR-021: emitir attestation request POST-COMMIT del `episodio_cerrado`.
            # Fail-soft: si Redis o el attestation-service estan caidos, log y continua.
            # El episodio queda cerrado en Postgres aunque la attestation se pierda
            # (recuperable via reconciliation job futuro).
            if attestation_payload is not None and self.attestation_producer is not None:
                await self.attestation_producer.publish(attestation_payload)

        except Exception as exc:
            # Contar intentos por mensaje usando XPENDING
            attempts = await self._get_attempts(message_id)
            if attempts >= MAX_ATTEMPTS:
                logger.error(
                    "Mensaje %s falló %d veces; moviendo a DLQ",
                    message_id,
                    attempts,
                    exc_info=exc,
                )
                await self._move_to_dlq(message_id, fields, str(exc), attempts)
                await self._ack(message_id)
            else:
                # Dejar sin ACK para que vuelva a entregarse al próximo XCLAIM/XREADGROUP
                logger.warning(
                    "Mensaje %s falló intento %d/%d; será reintentado",
                    message_id,
                    attempts,
                    MAX_ATTEMPTS,
                    exc_info=exc,
                )

    async def _persist_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Inserta Event en DB actualizando el Episode en la misma transaccion.

        Idempotencia: si (tenant_id, event_uuid) ya existe, se hace no-op.

        Returns:
            Payload de attestation request (ADR-021) si el evento es
            `episodio_cerrado` y se persistio exitosamente. None en otros casos
            (incluyendo idempotencia: un duplicado NO emite nueva attestation).
        """
        tenant_id = UUID(event["tenant_id"])
        episode_id = UUID(event["episode_id"])
        event_uuid = UUID(event["event_uuid"])
        seq = int(event["seq"])

        attestation_payload: dict[str, Any] | None = None

        async with tenant_session(tenant_id) as session:
            # 1. Cargar episodio con lock
            ep = await session.get(Episode, episode_id, with_for_update=True)
            if ep is None:
                # Auto-create el episodio si es el evento de apertura
                if event["event_type"] == "episodio_abierto":
                    ep = await self._create_episode(session, event)
                else:
                    raise ValueError(
                        f"Evento {event_uuid} seq={seq} para episodio inexistente {episode_id}"
                    )

            # 2. Validar seq esperado
            expected_seq = ep.events_count
            if seq != expected_seq:
                # Si el mismo evento ya fue persistido, es idempotencia OK
                existing = await session.execute(
                    select(Event).where(
                        Event.tenant_id == tenant_id,
                        Event.event_uuid == event_uuid,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    return None  # duplicado — ack sin hacer nada
                raise ValueError(
                    f"Seq inesperado: recibido={seq} esperado={expected_seq} "
                    f"para episodio {episode_id}"
                )

            # 3. Calcular hashes
            # Copia del evento sin los campos computados
            event_for_hash = {
                k: v
                for k, v in event.items()
                if k not in {"self_hash", "chain_hash", "prev_chain_hash"}
            }
            self_hash = compute_self_hash(event_for_hash)

            prev_chain = ep.last_chain_hash if seq > 0 else GENESIS_HASH
            chain_hash = compute_chain_hash(self_hash, prev_chain)

            # 4. Insertar evento (INSERT ... ON CONFLICT DO NOTHING para idempotencia)
            ts = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
            stmt = (
                insert(Event)
                .values(
                    tenant_id=tenant_id,
                    event_uuid=event_uuid,
                    episode_id=episode_id,
                    seq=seq,
                    event_type=event["event_type"],
                    ts=ts,
                    payload=event.get("payload", {}),
                    self_hash=self_hash,
                    chain_hash=chain_hash,
                    prev_chain_hash=prev_chain,
                    prompt_system_hash=event["prompt_system_hash"],
                    prompt_system_version=event["prompt_system_version"],
                    classifier_config_hash=event["classifier_config_hash"],
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "event_uuid"])
            )
            result = await session.execute(stmt)
            # SQLAlchemy 2.0 async: Result tiene rowcount para DML statements
            # pero el typed stub no lo expone explícitamente.
            if result.rowcount == 0:  # type: ignore[attr-defined]
                # Conflicto: evento duplicado, skip silencioso
                return None

            # 5. Actualizar el episodio
            ep.events_count = expected_seq + 1
            ep.last_chain_hash = chain_hash
            if event["event_type"] == "episodio_abandonado":
                # ADR-055 (fix 2026-06-10 #2): el abandono pausa el episodio en
                # vez de dejarlo "open" indefinido. El estudiante puede retomar
                # via POST /episodes/{id}/resume (tutor-service) y el docente lo
                # ve marcado "paused" en el analisis. Es metadata del Episode —
                # los eventos siguen append-only, sin tipos nuevos.
                ep.estado = "paused"
            elif event["event_type"] == "episodio_cerrado":
                ep.estado = "closed"
                ep.closed_at = utc_now()
                # ADR-021: capturar payload de attestation para emitir POST-COMMIT.
                # `event["ts"]` es el timestamp del cierre desde el emisor (formato Z).
                # `chain_hash` es el final_chain_hash de la cadena criptografica.
                # `ep.events_count` ya esta incrementado al total final.
                attestation_payload = {
                    "episode_id": str(episode_id),
                    "tenant_id": str(tenant_id),
                    "final_chain_hash": chain_hash,
                    "total_events": ep.events_count,
                    "ts_episode_closed": event["ts"],
                }
            elif event["event_type"] == "episodio_reabierto":
                # Reapertura docente (2026-06-19): revertia un episodio CERRADO a
                # "open" para que el alumno lo retome. La feature de reapertura fue
                # RETIRADA (2026-06-19): ya no hay endpoint ni UI que emita este
                # evento. Esta rama se conserva INERTE a proposito — append-only:
                # si quedara algun `episodio_reabierto` historico en la cadena, su
                # proyeccion de estado se sigue resolviendo bien (no rompe verify).
                ep.estado = "open"
                ep.closed_at = None
            elif ep.estado == "paused":
                # ADR-055: cualquier actividad posterior a un abandono reanuda
                # el episodio (el estudiante retomo via resume). No requiere
                # evento dedicado — la reanudacion es derivable de la cadena
                # (episodio_abandonado seguido de mas eventos).
                ep.estado = "open"

        # Salir del context manager → tenant_session hace commit. Si hubo
        # excepcion, attestation_payload sigue siendo None (no se emite).
        return attestation_payload

    async def _create_episode(self, session: AsyncSession, event: dict[str, Any]) -> Episode:
        """Crea el episodio al recibir el primer evento (episodio_abierto)."""
        payload = event.get("payload", {})
        # Idempotencia de apertura (fix episodios fantasma, 2026-06-17): persistir
        # el `ejercicio_id` del payload en `Episode.meta` para que el tutor-service
        # pueda buscar un episodio sin cerrar del mismo (alumno, problema, ejercicio)
        # SIN joinear contra la tabla `events`. Solo metadata mutable del Episode —
        # NO toca la cadena criptográfica (los eventos siguen append-only).
        meta: dict[str, Any] = {}
        ejercicio_id_raw = payload.get("ejercicio_id")
        if ejercicio_id_raw is not None:
            meta["ejercicio_id"] = str(ejercicio_id_raw)
        ep = Episode(
            id=UUID(event["episode_id"]),
            tenant_id=UUID(event["tenant_id"]),
            comision_id=UUID(payload["comision_id"]),
            student_pseudonym=UUID(payload["student_pseudonym"]),
            problema_id=UUID(payload["problema_id"]),
            prompt_system_hash=event["prompt_system_hash"],
            prompt_system_version=event["prompt_system_version"],
            classifier_config_hash=event["classifier_config_hash"],
            curso_config_hash=payload.get("curso_config_hash", "0" * 64),
            estado="open",
            meta=meta,
        )
        session.add(ep)
        await session.flush()
        return ep

    async def _get_attempts(self, message_id: str) -> int:
        """Pregunta a Redis cuántas veces se entregó este mensaje."""
        try:
            pending = await self.redis.xpending_range(
                self.stream_key,
                self.cfg.consumer_group,
                min=message_id,
                max=message_id,
                count=1,
            )
            if pending:
                # pending[0] es un dict con clave "times_delivered"
                return int(pending[0].get("times_delivered", 1))
        except Exception:
            pass
        return 1

    async def _move_to_dlq(
        self,
        message_id: str,
        fields: dict[bytes, bytes],
        error: str,
        attempts: int,
    ) -> None:
        """Mueve el mensaje a DLQ y marca el episodio como integrity_compromised."""
        raw = fields.get(b"payload") or fields.get(b"event") or b"{}"
        try:
            event_data = json.loads(raw)
        except json.JSONDecodeError:
            event_data = {"raw": raw.decode("utf-8", errors="replace")}

        # 1. Publicar en stream DLQ
        await self.redis.xadd(
            self.cfg.dlq_stream,
            {
                "original_stream": self.stream_key,
                "original_id": message_id,
                "error": error,
                "attempts": str(attempts),
                "payload": raw,
            },
        )

        # 2. Persistir en tabla dead_letters + marcar episodio como comprometido
        tenant_raw = event_data.get("tenant_id")
        episode_raw = event_data.get("episode_id")
        if tenant_raw and episode_raw:
            try:
                tenant_id = UUID(tenant_raw)
                episode_id = UUID(episode_raw)
                async with tenant_session(tenant_id) as session:
                    dl = DeadLetter(
                        tenant_id=tenant_id,
                        event_uuid=UUID(
                            event_data.get("event_uuid", "0" * 8 + "-0000-0000-0000-000000000000")
                        ),
                        episode_id=episode_id,
                        seq=int(event_data.get("seq", 0)),
                        raw_payload=event_data,
                        error_reason=error[:1000],
                        failed_attempts=attempts,
                        first_seen_at=utc_now(),
                    )
                    session.add(dl)

                    # Marcar episodio afectado (integrity_compromised = TRUE)
                    await session.execute(
                        update(Episode)
                        .where(Episode.id == episode_id)
                        .values(
                            integrity_compromised=True,
                            estado="integrity_compromised",
                        )
                    )

                # Métrica: incremento del counter post-commit. tenant_id como
                # único label (episode_id prohibido por cardinalidad).
                ctr_episodes_integrity_compromised_total.add(1, {"tenant_id": str(tenant_id)})

                # Desbloquear al alumno: sin sesión viva, el próximo acceso
                # entra por `resume_episode` y repone el contador de seq
                # desde `events_count`. Sin esto el episodio queda mudo —
                # cada evento nuevo nace con un seq que ya no puede entrar.
                # Fail-soft: el evento ya está en la DLQ y el episodio
                # marcado; no poder invalidar la sesión no debe frenar al
                # worker.
                try:
                    await self.redis.delete(f"{TUTOR_SESSION_KEY_PREFIX}{episode_id}")
                except Exception:
                    logger.warning(
                        "No se pudo invalidar la sesión del tutor para episodio %s",
                        episode_id,
                        exc_info=True,
                    )
            except Exception:
                logger.exception("Error guardando dead-letter en DB")

    async def _ack(self, message_id: str) -> None:
        """ACK al stream para que Redis lo quite del pending."""
        await self.redis.xack(self.stream_key, self.cfg.consumer_group, message_id)


async def run_worker(partition: int) -> None:
    """Entry-point para correr un worker particionado."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Resiliencia (FIX-20): health check + retry. No cambia la semántica de
    # consumer-group ni el single-writer por partición; solo la conexión.
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=False,
        health_check_interval=30,
        retry_on_timeout=True,
        socket_keepalive=True,
    )
    session_factory = get_session_factory()

    # ADR-021: producer del stream `attestation.requests`. Comparte el cliente
    # Redis del worker (misma DB). Si en algun ambiente este servicio no
    # quisiera attestation, simplemente no setea el producer (None default).
    attestation_producer = AttestationProducer(redis_client)

    worker = PartitionWorker(
        config=PartitionConfig(partition=partition),
        redis_client=redis_client,
        session_factory=session_factory,
        attestation_producer=attestation_producer,
    )

    # Graceful shutdown. asyncio.add_signal_handler no esta implementado en
    # Windows (ProactorEventLoop). En Windows el proceso se interrumpe via
    # Ctrl+C (KeyboardInterrupt) y termina sin shutdown ordenado del worker;
    # es aceptable en dev local. En Linux/macOS si registramos los handlers.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Windows: signal handlers via asyncio no soportados. Skip.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)

    try:
        await worker.run()
    finally:
        await redis_client.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CTR partition worker")
    parser.add_argument("--partition", type=int, required=True)
    args = parser.parse_args()

    asyncio.run(run_worker(args.partition))


if __name__ == "__main__":
    main()
