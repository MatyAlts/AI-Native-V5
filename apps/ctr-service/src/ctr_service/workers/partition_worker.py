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
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
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

# Contador atómico de seq del tutor-service (`SessionManager.SEQ_KEY_PREFIX`).
# El CTR normalmente no conoce keys de otro servicio; la excepción es
# deliberada, está acotada a un SET y se documenta acá.
#
# Cuando un evento no puede persistirse, ese contador queda adelantado
# respecto de `events_count` y TODO evento posterior del episodio se rechaza:
# el alumno sigue trabajando y nada se guarda. El worker es el único que sabe
# cuál es el valor correcto —lo tiene en `events_count`— así que lo repone
# directamente.
#
# Se repone el contador y NO se toca `tutor:session:`. El `seq` del JSON de
# sesión es un espejo no autoritativo (ver `SessionManager.next_seq`): el
# contador manda. Borrar la sesión sería peor por tres razones: dependería de
# que el frontend reanude (no lo hace para este estado), echaría al alumno de
# una sesión viva, y una request en vuelo la recrearía dejando el contador
# igual de desalineado.
#
# Reponer es además idempotente: si el mismo episodio manda N eventos a la
# DLQ, las N reposiciones escriben el mismo valor.
TUTOR_SEQ_KEY_PREFIX = "tutor:seq:"

# `SessionManager.SESSION_KEY_PREFIX`. Se usa SOLO en el camino de FALLO: si no
# se pudo reponer el contador, borrar la sesion es lo que deja que el heal del
# tutor lo reconstruya en el evento siguiente. Sin eso el episodio queda mudo
# hasta que venza el TTL — seis horas.
TUTOR_SESSION_KEY_PREFIX = "tutor:session:"

# TTL del contador, espejado de `SessionManager.SESSION_TTL` (6 h). Si se
# repusiera sin TTL la key quedaría para siempre; si se repusiera con uno más
# corto, expiraría antes que la sesión que la acompaña.
TUTOR_SEQ_TTL_SECONDS = 6 * 3600

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

    async def _reponer_contador_seq(self, episode_id: UUID, tenant_id: UUID) -> None:
        """Repone el contador de seq del tutor al `events_count` del episodio.

        Es el heal del incidente de desincronización: el tutor asigna el seq
        con `INCR tutor:seq:{episode_id}` y el worker lo valida contra
        `episodes.events_count`. Cuando un evento no entra, el contador ya lo
        contó y la cadena no, y desde ahí todo lo que el alumno escriba se
        rechaza. El worker es el único de los dos que sabe cuál es el valor
        correcto.

        Escribe `events_count` — el próximo `INCR` devolverá `events_count + 1`
        y `next_seq` entregará `events_count`, que es exactamente lo que la
        cadena espera a continuación.

        Fail-soft y sin excepciones hacia afuera: llega desde `_move_to_dlq`,
        donde el evento ya está archivado y el episodio marcado. Un fallo acá
        deja el episodio bloqueado —el estado previo al fix— pero no debe
        frenar la ingesta del resto.
        """
        try:
            async with tenant_session(tenant_id) as session:
                ep = await session.get(Episode, episode_id)
                if ep is None:
                    return
                events_count = int(ep.events_count)

            await self.redis.set(
                f"{TUTOR_SEQ_KEY_PREFIX}{episode_id}",
                events_count,
                ex=TUTOR_SEQ_TTL_SECONDS,
            )
            logger.info(
                "Contador de seq repuesto a %d para episodio %s",
                events_count,
                episode_id,
            )
        except Exception:
            logger.warning(
                "No se pudo reponer el contador de seq del episodio %s; "
                "se intenta borrar la sesion para que el tutor la reconstruya",
                episode_id,
                exc_info=True,
            )
            await self._forzar_reconstruccion_de_sesion(episode_id)

    async def _forzar_reconstruccion_de_sesion(self, episode_id: UUID) -> None:
        """Ultimo recurso cuando no se pudo reponer el contador.

        **Sin esto, el episodio quedaba mudo seis horas.** El worker repone el
        contador y NO toca `tutor:session:` — eso es correcto en el camino feliz
        (borrar la sesion echaria al alumno de una sesion viva). Pero si la
        reposicion falla —Postgres saturado, que es plausible: acabamos de
        fallar tres veces contra la misma base— el resultado era:

          - el contador queda adelantado y TODO evento posterior se rechaza;
          - la sesion sigue viva, asi que `_emitir_con_heal` nunca dispara (solo
            entra por `ValueError`, y ese `ValueError` sale de `sessions.get()`
            devolviendo `None`);
          - y aunque el alumno apriete "retomar", `resume_episode` tiene un
            early-return idempotente ANTES de `init_seq_counter`: devuelve 200
            sin tocar el contador.

        O sea que el unico camino de salida era el TTL de la sesion: seis horas
        con el alumno tipeando y nada guardandose.

        Borrar la sesion invierte eso: el proximo evento encuentra `None`,
        levanta `ValueError`, y el heal reconstruye la sesion Y el contador
        desde `events_count`. El alumno pierde el estado en memoria de la
        sesion —que es reconstruible— en vez de perder su trabajo.

        Si esto tambien falla, el log sube a ERROR: ahi si el episodio queda
        trabado y alguien tiene que enterarse.
        """
        try:
            await self.redis.delete(f"{TUTOR_SESSION_KEY_PREFIX}{episode_id}")
            logger.info(
                "Sesion del episodio %s borrada: el proximo evento reconstruye "
                "sesion y contador via el heal del tutor",
                episode_id,
            )
        except Exception:
            logger.error(
                "El episodio %s quedo TRABADO: no se pudo reponer el contador de "
                "seq ni borrar su sesion. Todo evento nuevo se va a rechazar "
                "hasta que venza el TTL de la sesion.",
                episode_id,
                exc_info=True,
            )

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

    @staticmethod
    def _es_transitorio(exc: BaseException) -> bool:
        """¿El fallo es de INFRAESTRUCTURA, o del contenido del mensaje?

        La diferencia decide si el mensaje puede ir a la DLQ, y no es un matiz:
        **un evento que va a la DLQ sale de la cadena para siempre**, y su lugar
        lo termina ocupando otro (el heal repone el contador al `events_count`).

        - **Permanente** — `ValueError` de `_persist_event` (seq inesperado,
          episodio inexistente), JSON roto, campos que faltan. Reintentar
          devuelve exactamente lo mismo. La DLQ es la respuesta correcta.
        - **Transitorio** — Postgres cortado, pool agotado, DNS, Redis caído.
          El mensaje es VÁLIDO; lo único que pasa es que ahora no se puede
          escribir.

        Por qué importa tanto acá: hasta que se agregó el reclamo de pendientes,
        `MAX_ATTEMPTS` era inalcanzable y la DLQ por fallo de procesamiento era
        código muerto. Al encenderla, el presupuesto total pasó a ser
        `1 entrega + 2 reclamos × 60s de idle ≈ 120 segundos`, plano y sin
        backoff. Un failover de Postgres de tres minutos —que pasa— mandaba a
        la DLQ TODOS los eventos de esa ventana y marcaba decenas de episodios
        como adulterados. Eventos perfectamente válidos, de alumnos que estaban
        trabajando bien.

        Antes del reclamo esos mensajes se quedaban en la PEL, intactos y
        recuperables con un `XCLAIM` manual cuando la base volvía. El fix del
        retry no puede costar eso.

        Ante un transitorio se reintenta SIN TOPE. Es deliberado: la alternativa
        es tirar evidencia de la tesis porque la base tardó en volver. El
        mensaje queda en la PEL —visible en `XPENDING`, que es donde un
        operador lo busca— y el log lo dice en cada vuelta.
        """
        if isinstance(exc, OperationalError | InterfaceError):
            return True
        if isinstance(exc, DBAPIError) and exc.connection_invalidated:
            return True
        # `redis.RedisError` y los `OSError` de red (incluye `ConnectionError`
        # y `TimeoutError`, que en Python 3.11+ heredan de `OSError`).
        return isinstance(exc, redis.RedisError | OSError)

    @staticmethod
    def _causa_del_hueco(error: str) -> str:
        """Por que este evento no entro en la cadena.

        POR QUE HACE FALTA (QA 2026-08-31)
        ----------------------------------
        `_move_to_dlq` marca `integrity_compromised=True`. Como registro tecnico
        es correcto —el hueco en la cadena existio— pero la palabra se lee como
        **"este alumno hizo trampa"**, y en el piloto eso es una acusacion sobre
        una persona real.

        Y NINGUNA de las causas que llegan hasta aca es adulteracion. La
        adulteracion la detecta el integrity-checker comparando hashes ya
        persistidos, no el worker de ingesta. Ademas, `_es_transitorio` ya
        garantiza que un fallo de infraestructura NO llegue a la DLQ. Lo que
        queda es siempre un problema NUESTRO: un evento cuyo `seq` no encaja, un
        episodio que no existe, un payload mal armado.

        O sea que hoy el flag se prende exclusivamente por fallas propias, y se
        lee como sospecha sobre el alumno. Esto no cambia el flag —es un
        invariante documentado (RN-039/RN-040) y el hueco realmente ocurrio—
        pero deja escrito, en la fila de la DLQ y en el log, de que familia es.

        No adivina: se apoya en el texto del error que ya se guardaba en
        `error_reason` y solo lo rotula.
        """
        e = error.lower()
        if "seq" in e or "expected" in e or "esperado" in e:
            # El caso tipico: la cadena esperaba N y llego otro. Es una perdida
            # de evento aguas arriba, o una carrera del contador — nuestra.
            return "hueco_de_ingesta"
        if "episode" in e or "episodio" in e or "not found" in e or "no existe" in e:
            return "episodio_ausente"
        return "evento_no_procesable"

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
            if self._es_transitorio(exc):
                # NO consume presupuesto. El mensaje es valido; lo que fallo es
                # la infraestructura, y mandarlo a la DLQ seria tirar un evento
                # bueno porque la base tardo en volver.
                logger.warning(
                    "Mensaje %s: fallo TRANSITORIO (intento %d). Queda en la PEL "
                    "y se reintenta sin tope; no cuenta para la DLQ.",
                    message_id,
                    attempts,
                    exc_info=exc,
                )
                return
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
            elif ep.estado in ("paused", "integrity_compromised"):
                # ADR-055: cualquier actividad posterior a un abandono reanuda
                # el episodio (el estudiante retomo via resume). No requiere
                # evento dedicado — la reanudacion es derivable de la cadena
                # (episodio_abandonado seguido de mas eventos).
                #
                # `integrity_compromised` se repone por el mismo criterio: lo
                # pone `_move_to_dlq` cuando un evento no entro en la cadena, y
                # que llegue un evento posterior significa que el contador de
                # seq volvio a alinearse y el episodio esta operativo otra vez.
                #
                # Dejarlo pegado en ese estado tiene un costo que no se ve: hay
                # consultas que filtran por `estado IN ('closed','paused')`, asi
                # que el episodio DESAPARECE de la vista del docente y del
                # progreso del alumno — no aparece marcado, no aparece. La
                # bandera `integrity_compromised` del episodio NO se toca: ahi
                # queda registrado el hueco, que es lo que hay que preservar.
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
        """Mueve el mensaje a DLQ y marca el episodio como integrity_compromised.

        `integrity_compromised` NO significa que el alumno haya adulterado nada.
        Ver `_causa_del_hueco`: todo lo que llega hasta aca es una falla de
        ingesta nuestra, y la causa concreta queda rotulada en la fila de la DLQ
        y en el log para que nadie tenga que deducirla de la palabra.
        """
        causa = self._causa_del_hueco(error)
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
                "causa": causa,
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
                        # El rotulo va PRIMERO y en el mismo campo que ya
                        # existia: sin migracion, y visible para quien lea la
                        # fila sin tener que interpretar un stack trace.
                        error_reason=f"[{causa}] {error}"[:1000],
                        failed_attempts=attempts,
                        first_seen_at=utc_now(),
                    )
                    session.add(dl)

                    # Marcar episodio afectado (integrity_compromised = TRUE).
                    #
                    # La bandera se pone siempre — el hueco en la cadena
                    # ocurrio y hay que registrarlo. El `estado`, en cambio,
                    # NO se pisa si el episodio ya cerro: un mensaje viejo que
                    # llega tarde a la DLQ lo des-cerraria, dejando
                    # `closed_at` seteado con otro estado y rompiendo la
                    # reflexion final, que exige `estado == "closed"`. Con el
                    # reclamo de pendientes activo esto dejo de ser
                    # improbable: los mensajes viejos ahora si se reprocesan.
                    await session.execute(
                        update(Episode)
                        .where(Episode.id == episode_id)
                        .values(integrity_compromised=True)
                    )
                    await session.execute(
                        update(Episode)
                        .where(Episode.id == episode_id, Episode.estado != "closed")
                        .values(estado="integrity_compromised")
                    )

                # Métrica: incremento del counter post-commit. tenant_id como
                # único label (episode_id prohibido por cardinalidad).
                # `causa` como label junto al tenant: sin ella, el dashboard
                # muestra un contador de "episodios comprometidos" que no
                # distingue nada y se lee como cantidad de sospechosos.
                # `episode_id` sigue prohibido por cardinalidad; `causa` es un
                # enum de tres valores.
                ctr_episodes_integrity_compromised_total.add(
                    1, {"tenant_id": str(tenant_id), "causa": causa}
                )
                logger.error(
                    "ctr_hueco_en_la_cadena episodio=%s causa=%s intentos=%s — "
                    "NO es adulteracion del alumno: es una falla de ingesta nuestra",
                    episode_id,
                    causa,
                    attempts,
                )

                # Desbloquear al alumno reponiendo el contador de seq al
                # valor que la cadena espera. Sin esto el episodio queda mudo:
                # cada evento nuevo nace con un seq que ya no puede entrar, y
                # el alumno escribe sin que nada se guarde.
                #
                # Fail-soft: el evento ya está en la DLQ y el episodio quedó
                # marcado; no poder reponer el contador no debe frenar al
                # worker.
                await self._reponer_contador_seq(episode_id, tenant_id)
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
