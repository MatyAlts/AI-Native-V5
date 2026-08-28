"""Session manager del tutor.

El tutor mantiene una sesión por episodio con:
- seq actual (próximo evento a publicar)
- mensajes previos de la conversación (para contexto multi-turno)

Estado en Redis con TTL de 6h (las sesiones típicas duran <1h). Al
cerrar episodio o al expirar, el state se elimina; la fuente de verdad
histórica es el CTR en Postgres.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import WatchError

logger = logging.getLogger(__name__)

SESSION_TTL = 6 * 3600  # 6 horas

# ADR-025 (G10-A): clave bajo la cual se almacenan las sesiones del tutor.
# El worker de abandono escanea con MATCH sobre este prefijo + "*".
SESSION_KEY_PREFIX = "tutor:session:"

# Distraction tracking: cuando el alumno pierde foco de la pestaña, guardamos
# el timestamp UTC en una key separada. El distraction_worker (server-side)
# la barre cada few seconds y cierra el episodio si supera el umbral.
DISTRACTION_KEY_PREFIX = "tutor:distraction:"
DISTRACTION_TTL = 30 * 60  # 30 min sanity cap

# Idempotency-Key server-side (fix P-17). La cola offline del ctr-client
# reintenta el MISMO evento (mismo `event_uuid` de cliente) cuando pierde el
# ACK de una request que el servidor SÍ persistió. Sin dedup, cada reintento
# vuelve a llamar a `next_seq()` y avanza el contador de sesión, dejando un
# hueco en la secuencia que el partition_worker no puede cerrar → el episodio
# termina `integrity_compromised` de forma permanente. Guardamos por episodio
# un hash `client_event_uuid -> seq_asignado` con TTL acotado; el reintento
# devuelve el mismo seq SIN avanzar el contador ni re-publicar al CTR.
SEEN_KEY_PREFIX = "tutor:seen:"
SEEN_TTL = SESSION_TTL  # mismo horizonte que la sesión (6h)

# Claim de abandono (ADR-025 G10-A, fix del TOCTOU). La idempotencia del
# abandono estaba apoyada en el estado de sesión: el primero borra la sesión, el
# segundo la encuentra ausente. Eso vale sólo si las dos llamadas se serializan,
# y no se serializan — entre el `get()` y el `delete()` hay un publish al CTR
# entero. Esta key elige al emisor con un `SET NX` atómico. Se libera al abrir o
# reanudar el episodio (`init_seq_counter`), no al emitir: el claim acompaña el
# ciclo de vida del episodio, no el de la request.
ABANDONO_KEY_PREFIX = "tutor:abandono:"

# FIX A (keystone) — contador de seq ATÓMICO por episodio.
#
# El seq de la cadena CTR DEBE ser contiguo y sin huecos (el partition_worker
# valida `expected_seq == events_count`). Antes de este fix el seq salía de un
# read-modify-write sobre el JSON de sesión (`current = state.seq; state.seq +=
# 1; set()`), que NO es atómico: dos coroutines concurrentes sobre el mismo
# episodio (p. ej. el POST de fondo del ctr-client en paralelo con el SSE de
# `/message`, o dos pestañas compartiendo la cola offline) leían el MISMO
# `state.seq` y reservaban el MISMO seq → dos eventos con igual seq → hueco →
# dead-letter → `integrity_compromised` PERMANENTE.
#
# Ahora el contador autoritativo es esta key Redis manipulada con INCR (atómico
# aun ante concurrencia y aun entre réplicas del tutor-service). Convención: la
# key vale la CANTIDAD de seqs ya reservados (= el próximo seq a asignar). Como
# `INCR` devuelve el valor DESPUÉS de incrementar, el seq reservado es
# `INCR - 1`. Se inicializa en `open_episode`/`resume_episode` (fresh=0,
# resume=events_count) para arrancar del max seq ya persistido — NUNCA se
# resetea a 0 sobre un episodio con historia.
SEQ_KEY_PREFIX = "tutor:seq:"

# Idempotencia atómica (FIX A parte 2). El claim en `tutor:seen:{episode_id}`
# se hace con HSETNX (atómico) ANTES de reservar el seq: el que gana el claim
# reserva (INCR) y guarda uuid→seq; el que pierde LEE el seq ya asignado. Así
# dos event_uuid DISTINTOS obtienen seqs contiguos distintos y el MISMO
# event_uuid concurrente NO gasta un seq de más (sin hueco, sin duplicado).
# Mientras el ganador está reservando, el registro vale este sentinel; el
# perdedor espera con backoff hasta que el ganador lo resuelve al seq real.
_SEEN_PENDING = "PENDING"
_SEEN_RESOLVE_MAX_RETRIES = 50
_SEEN_RESOLVE_BACKOFF_SECONDS = 0.02  # hasta ~1s de espera total del perdedor


class SeqReservationPendingError(Exception):
    """El ganador del claim de idempotencia no resolvió el seq a tiempo.

    Caso degenerado y raro (típicamente el ganador vive en OTRA réplica del
    tutor-service y está lento o murió mid-reserva). Fail-safe: NO emitimos un
    duplicado ni inventamos un seq (ambos romperían la integridad de la
    cadena). Señalamos al caller para que reintente más tarde — el ctr-client
    reintenta el POST y, para entonces, el claim está resuelto (mismo seq) o
    liberado (se puede re-ganar). El route lo mapea a 503.
    """

    def __init__(self, episode_id: UUID, idempotency_key: str) -> None:
        super().__init__(
            f"reserva de seq pendiente para episode={episode_id} "
            f"idempotency_key={idempotency_key}; reintentar"
        )
        self.episode_id = episode_id
        self.idempotency_key = idempotency_key


@dataclass
class SessionState:
    episode_id: UUID
    tenant_id: UUID
    comision_id: UUID
    student_pseudonym: UUID
    seq: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    prompt_system_hash: str = ""
    prompt_system_version: str = ""
    classifier_config_hash: str = ""
    curso_config_hash: str = ""
    model: str = ""  # seleccionado por feature flag en open_episode
    # ADR-040 (Sec 6.2 epic ai-native-completion-and-byok): cacheado al abrir el
    # episodio para no re-resolver `episode → tarea → comision → materia` en
    # cada turno. None = no se pudo resolver (degrada a tenant_fallback en BYOK).
    materia_id: UUID | None = None
    # ADR-025: epoch UTC de la ultima actividad. Lo refresca `set()` (que
    # lo invocan `open_episode` y `next_seq`). Sirve al worker de abandono
    # para detectar sesiones inactivas y emitir EpisodioAbandonado(reason=timeout).
    last_activity_at: float = field(default_factory=time.time)
    # ADR-047: UUID del Ejercicio reusable del banco standalone (None = TP
    # monolítica sin ejercicio asociado). Es la identidad permanente del
    # ejercicio que el estudiante está resolviendo.
    ejercicio_id: UUID | None = None
    # Orden del ejercicio dentro de la TP (denormalizado desde tp_ejercicios).
    # Necesario para validación de secuencialidad y para el payload del CTR
    # hasta que ADR-049 sume `ejercicio_id` al payload (Batch 6).
    ejercicio_orden: int | None = None
    # tutor-context-rag-rubrica: rubrica formateada para inyectar al LLM. Se
    # resuelve al abrir el episodio y se cachea aqui (best-effort; None = no
    # se pudo resolver o la TP no tiene rubrica).
    rubrica_context: str | None = None
    # 2026-05-21 — código actual del editor del alumno. Se actualiza con cada
    # evento `edicion_codigo` que llega al CTR. Se inyecta como `system`
    # message en el siguiente prompt al tutor para que pueda referirse a
    # líneas específicas ("en la línea 7 estás haciendo X"). None = el alumno
    # no escribió nada todavía en este episodio.
    current_code: str | None = None


class SessionManager:
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def _key(self, episode_id: UUID) -> str:
        return f"{SESSION_KEY_PREFIX}{episode_id}"

    async def get(self, episode_id: UUID) -> SessionState | None:
        raw = await self.redis.get(self._key(episode_id))
        if raw is None:
            return None
        data = json.loads(raw)
        materia_raw = data.get("materia_id")
        ejercicio_raw = data.get("ejercicio_id")
        return SessionState(
            episode_id=UUID(data["episode_id"]),
            tenant_id=UUID(data["tenant_id"]),
            comision_id=UUID(data["comision_id"]),
            student_pseudonym=UUID(data["student_pseudonym"]),
            seq=data["seq"],
            messages=data["messages"],
            prompt_system_hash=data["prompt_system_hash"],
            prompt_system_version=data["prompt_system_version"],
            classifier_config_hash=data["classifier_config_hash"],
            curso_config_hash=data["curso_config_hash"],
            model=data.get("model", ""),
            # ADR-040: sesiones legacy (pre-Sec 6.2) no tienen materia_id
            # — fallback a None (degrada a tenant_fallback en BYOK).
            materia_id=UUID(materia_raw) if materia_raw else None,
            # last_activity_at puede no existir en sesiones pre-ADR-025
            # — fallback a time.time() para que sesiones legacy NO disparen
            # abandono inmediato en el primer pase del worker.
            last_activity_at=data.get("last_activity_at", time.time()),
            # ADR-047: sesiones legacy no tienen ejercicio_id.
            ejercicio_id=UUID(ejercicio_raw) if ejercicio_raw else None,
            ejercicio_orden=data.get("ejercicio_orden"),
            # tutor-context-rag-rubrica: sesiones legacy no tienen rubrica_context.
            rubrica_context=data.get("rubrica_context"),
            # Sesiones legacy no tienen current_code — default None.
            current_code=data.get("current_code"),
        )

    async def set(self, state: SessionState) -> None:
        # ADR-025: refrescar last_activity_at en cada persistencia. Como
        # `set()` se invoca desde `open_episode` (creacion) y desde
        # `next_seq` (cada evento del CTR), esto cubre toda la actividad
        # observable del estudiante via el tutor.
        state.last_activity_at = time.time()
        data = {
            "episode_id": str(state.episode_id),
            "tenant_id": str(state.tenant_id),
            "comision_id": str(state.comision_id),
            "student_pseudonym": str(state.student_pseudonym),
            "seq": state.seq,
            "messages": state.messages,
            "prompt_system_hash": state.prompt_system_hash,
            "prompt_system_version": state.prompt_system_version,
            "classifier_config_hash": state.classifier_config_hash,
            "curso_config_hash": state.curso_config_hash,
            "model": state.model,
            "materia_id": str(state.materia_id) if state.materia_id else None,
            "last_activity_at": state.last_activity_at,
            "ejercicio_id": str(state.ejercicio_id) if state.ejercicio_id else None,
            "ejercicio_orden": state.ejercicio_orden,
            "rubrica_context": state.rubrica_context,
            "current_code": state.current_code,
        }
        await self.redis.setex(self._key(state.episode_id), SESSION_TTL, json.dumps(data))

    async def delete(self, episode_id: UUID) -> None:
        # Borra la sesión y su contador de seq atómico. El registro de
        # idempotencia (`tutor:seen:`) se deja vencer por TTL — un reintento
        # tardío del ctr-client sobre un episodio ya cerrado igual encuentra
        # `session=None` y el route responde 409/404 sin tocar el contador.
        await self.redis.delete(self._key(episode_id), self._seq_key(episode_id))

    # ── Contador de seq atómico por episodio (FIX A) ────────────────────

    def _seq_key(self, episode_id: UUID) -> str:
        return f"{SEQ_KEY_PREFIX}{episode_id}"

    async def init_seq_counter(self, episode_id: UUID, next_seq: int) -> None:
        """Inicializa el contador atómico de seq del episodio. **Nunca lo baja.**

        `next_seq` = cantidad de seqs ya reservados = próximo seq a asignar.
        `open_episode` lo llama con 0 (episodio nuevo); `resume_episode` con el
        `events_count` persistido (arranca del max seq ya en la cadena, NUNCA
        resetea a 0).

        **Era un SET incondicional**, y su docstring decía que "el caller
        garantiza" que éste es el punto de inicialización. Eso valía cuando los
        callers eran dos y explícitos: abrir el episodio y un `POST /resume`. El
        heal de sesión lo convirtió en OCHO callers implícitos y CONCURRENTES
        —los siete `emit_*` más `send_message`, vía `_emitir_con_heal`— y
        ninguno garantiza nada: el `existing is not None` de `resume_episode` es
        un check-then-act con dos `await` de red en el medio.

        La carrera, con la sesión vencida por TTL y `events_count = N`:

            A: POST /message          -> get()=None -> arranca resume
            B: POST /edicion_codigo   -> get()=None -> arranca resume
            B: set(state); init(N)                      [contador = N]
            B: next_seq -> INCR -> N+1 -> publica seq=N
            A: set(state); init(N)          <- REGRESION del contador a N
            A: next_seq -> INCR -> N+1 -> publica seq=N   <- DUPLICADO

        Dos eventos distintos con el mismo seq: el worker persiste uno, el otro
        va a la DLQ y marca el episodio `integrity_compromised`. El bug que este
        epic viene a cerrar, reintroducido por su propio heal. Y no es un borde:
        el frontend emite `edicion_codigo` con debounce mientras el alumno
        charla con el tutor.

        Ahora es un compare-and-set: escribe sólo si el contador está AUSENTE o
        vale MENOS. Si vale más, alguien reservó en el medio y se respeta —
        bajarlo es lo único que produce el duplicado. El TTL se refresca igual.

        Acá también se libera el claim de abandono (ver `claim_abandono`): abrir
        o reanudar el episodio empieza un ciclo nuevo, y un episodio pausado que
        el alumno retoma tiene que poder volver a abandonarse. Ese borrado va
        SIEMPRE, gane o pierda el CAS: es del ciclo de vida del episodio, no del
        contador.
        """
        key = self._seq_key(episode_id)
        try:
            async with self.redis.pipeline() as pipe:
                await pipe.watch(key)
                actual = await pipe.get(key)
                if isinstance(actual, bytes):
                    actual = actual.decode("utf-8")
                ya_reservo_mas = actual is not None and int(actual) >= next_seq
                pipe.multi()
                if not ya_reservo_mas:
                    pipe.set(key, next_seq, ex=SESSION_TTL)
                else:
                    pipe.expire(key, SESSION_TTL)
                await pipe.execute()
                if ya_reservo_mas:
                    logger.info(
                        "init_seq_counter del episodio %s NO baja el contador: "
                        "vale %s y se pidio %s (hubo una reserva concurrente).",
                        episode_id,
                        actual,
                        next_seq,
                    )
        except WatchError:
            # Otro caller lo movio mientras mirabamos. Su valor es al menos tan
            # nuevo como el nuestro; el unico daño posible seria pisarlo hacia
            # abajo, asi que no se reintenta.
            logger.info(
                "init_seq_counter del episodio %s perdio el CAS; se respeta el "
                "valor del otro caller.",
                episode_id,
            )
        await self.redis.delete(self._abandono_key(episode_id))

    # ── Claim de abandono (ADR-025, TOCTOU) ─────────────────────────────

    def _abandono_key(self, episode_id: UUID) -> str:
        return f"{ABANDONO_KEY_PREFIX}{episode_id}"

    async def claim_abandono(self, episode_id: UUID) -> bool:
        """Elige ATÓMICAMENTE quién emite el `episodio_abandonado` del episodio.

        La idempotencia del abandono (ADR-025 G10-A) estaba escrita como «la
        primera emisión borra la sesión, la segunda encuentra `session=None` y
        no emite». Eso asume que las dos llamadas se serializan, y no se
        serializan: entre el `sessions.get()` y el `sessions.delete()` hay una
        publicación al CTR entera. Dos POST concurrentes —`beforeunload` y
        `pagehide` del mismo cierre, dos pestañas, el worker de timeout pisándose
        con el frontend— pasan los dos por el `if state is None` antes de que
        ninguno borre, y la cadena termina con DOS `episodio_abandonado`.

        `SET NX` resuelve la eleccion en una sola operación: gana uno solo, aun
        entre réplicas distintas del tutor-service. El claim se libera al abrir
        o reanudar el episodio (`init_seq_counter`), no al emitir — así el ciclo
        de vida del claim acompaña al del episodio y no al de la request.

        Es deliberado que esto NO dependa de un `Idempotency-Key` del cliente:
        los dos emisores del ADR-025 son procesos distintos (frontend y worker
        server-side) que jamás podrían coordinar una clave común.
        """
        ganado = await self.redis.set(self._abandono_key(episode_id), "1", nx=True, ex=SESSION_TTL)
        return bool(ganado)

    async def release_abandono(self, episode_id: UUID) -> None:
        """Libera el claim de abandono (el emisor ganador no llegó a publicar).

        Sin esto, un fallo del CTR dejaría el episodio sin poder abandonarse
        nunca: el claim quedaría tomado por un intento que no emitió nada.
        """
        await self.redis.delete(self._abandono_key(episode_id))

    async def next_seq(self, state: SessionState) -> int:
        """Reserva ATÓMICAMENTE el próximo seq del episodio vía Redis INCR.

        Devuelve el seq a usar para el próximo evento. El contador autoritativo
        es la key `tutor:seq:{episode_id}` (ver SEQ_KEY_PREFIX): `INCR` es
        atómico aun ante coroutines/réplicas concurrentes, así que dos llamadas
        concurrentes sobre el mismo episodio obtienen seqs distintos y
        contiguos — nunca el mismo seq (que era el bug read-modify-write).

        Como la key vale la cantidad de seqs ya reservados y `INCR` devuelve el
        valor DESPUÉS de incrementar, el seq reservado es `INCR - 1`. Sobre una
        key ausente `INCR` arranca en 0→1 (reserva seq 0), consistente con un
        episodio recién inicializado con `init_seq_counter(..., 0)`.

        Sigue refrescando `last_activity_at` (vía `set()`) — contrato del worker
        de abandono (ADR-025), que detecta inactividad por ese timestamp. El
        `state.seq` en el JSON queda como espejo NO autoritativo; el contador
        Redis es la única fuente de verdad para la asignación.
        """
        key = self._seq_key(state.episode_id)
        new_val = await self.redis.incr(key)
        await self.redis.expire(key, SESSION_TTL)
        state.seq = new_val  # espejo no-autoritativo (el contador Redis manda)
        await self.set(state)
        return new_val - 1

    async def release_seq(self, episode_id: UUID, seq: int) -> bool:
        """Devuelve al contador un seq reservado que NO llegó a publicarse.

        `next_seq` reserva ANTES de que el evento salga hacia el ctr-service.
        Si el publish falla (red, 5xx, timeout — `publish_event` hace
        `raise_for_status`) el número quedaba quemado: nadie lo devolvía y el
        próximo evento nacía en `reservado + 1`. El partition_worker espera
        `seq == events_count`, no matchea, reintenta 3 veces, manda a la DLQ y
        marca el episodio `integrity_compromised`. Un episodio SANO terminaba
        etiquetado como adulterado y desaparecía de las vistas de docente y
        alumno — para una tesis sobre trazabilidad criptográfica eso es
        corrupción, no una molestia operativa.

        La compensación es un DECR **condicionado** (compare-and-decrement con
        WATCH/MULTI): sólo devolvemos el número si el contador sigue valiendo
        `seq + 1`, es decir si somos el último que reservó. Un DECR incondicional
        sería peor que el hueco: si otra coroutine reservó `seq + 1` mientras
        publicábamos, bajar el contador haría que el evento siguiente naciera
        con un seq YA usado → dos eventos con el mismo seq, que es exactamente
        el defecto que FIX A vino a cerrar.

        Cuando el CAS pierde (hubo una reserva concurrente) el hueco es real y
        no se puede cerrar desde acá: lo logueamos en ERROR para que quede
        rastro, y el `_reponer_contador_seq` del partition_worker sigue siendo
        la red de abajo. Devuelve True si compensó, False si no pudo.
        """
        key = self._seq_key(episode_id)
        esperado = str(seq + 1)
        try:
            async with self.redis.pipeline() as pipe:
                await pipe.watch(key)
                actual = await pipe.get(key)
                if isinstance(actual, bytes):
                    actual = actual.decode("utf-8")
                if actual != esperado:
                    await pipe.unwatch()
                    logger.error(
                        "no se pudo devolver el seq %s del episodio %s: el contador "
                        "vale %r y no %r (hubo una reserva concurrente). Queda un "
                        "hueco en la cadena; lo repone el partition_worker.",
                        seq,
                        episode_id,
                        actual,
                        esperado,
                    )
                    return False
                pipe.multi()
                pipe.decr(key)
                pipe.expire(key, SESSION_TTL)
                await pipe.execute()
                return True
        except WatchError:
            logger.error(
                "no se pudo devolver el seq %s del episodio %s: el contador cambió "
                "durante la compensación. Queda un hueco en la cadena.",
                seq,
                episode_id,
            )
            return False

    async def reserve_or_get_seq(
        self,
        episode_id: UUID,
        idempotency_key: str | None,
        emit: Callable[[], Awaitable[int]],
    ) -> int:
        """Idempotencia ATÓMICA para la emisión de un evento CTR (FIX A).

        Garantiza que, ante N coroutines concurrentes con el MISMO
        `idempotency_key` sobre el mismo episodio, EXACTAMENTE UNA reserva un
        seq (vía `emit`, que hace `next_seq` + publish) y las demás devuelven
        ESE MISMO seq sin reservar uno nuevo — no se desperdicia ningún seq
        (sin hueco) ni se re-publica el evento (sin duplicado).

        Mecanismo:
          1. `HSETNX seen:{episode_id} {key} PENDING` — claim atómico. Reemplaza
             el viejo check-then-act (`get_seen_seq`→`emit`→`mark_seen`), que NO
             era atómico: dos coroutines con el mismo uuid veían `seen=None` y
             ambas emitían.
          2. Ganador (HSETNX=1): `emit()` (reserva seq + publica) →
             `HSET ... {key} <seq>` resuelve el claim → devuelve seq. Si `emit()`
             falla, `HDEL` libera el claim (un reintento genuino podrá re-ganarlo)
             y se re-propaga la excepción.
          3. Perdedor (HSETNX=0): `HGET`; si es número lo devuelve; si sigue
             PENDING espera con backoff hasta que el ganador lo resuelva.

        Sin `idempotency_key` (None) el comportamiento es el legacy: `emit()`
        directo, sin dedup (callers que no mandan la clave no cambian).
        """
        if not idempotency_key:
            return await emit()

        seen_key = self._seen_key(episode_id)
        won = await self.redis.hsetnx(seen_key, idempotency_key, _SEEN_PENDING)
        if won:
            await self.redis.expire(seen_key, SEEN_TTL)
            try:
                seq = await emit()
            except Exception:
                # Liberar el claim para que un reintento genuino pueda re-ganarlo.
                await self.redis.hdel(seen_key, idempotency_key)
                raise
            await self.redis.hset(seen_key, idempotency_key, str(seq))
            await self.redis.expire(seen_key, SEEN_TTL)
            return seq

        # Perdimos el claim: otra coroutine con el mismo uuid ya reservó (o está
        # reservando) el seq. Leerlo, esperando si todavía está PENDING.
        for _ in range(_SEEN_RESOLVE_MAX_RETRIES):
            raw = await self.redis.hget(seen_key, idempotency_key)
            if raw is not None and raw != _SEEN_PENDING:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    break  # valor corrupto → fail-safe hacia SeqReservationPendingError
            await asyncio.sleep(_SEEN_RESOLVE_BACKOFF_SECONDS)
        raise SeqReservationPendingError(episode_id, idempotency_key)

    # ── Idempotencia por Idempotency-Key (fix P-17) ─────────────────────
    #
    # NOTA: la vía viva de dedup es `reserve_or_get_seq` (claim atómico HSETNX,
    # FIX A). `get_seen_seq`/`mark_seen` quedan como primitivas de storage de
    # bajo nivel (lectura/escritura del registro seq) — ya NO son el flujo de
    # dedup del route (ese era el check-then-act con race que FIX A reemplazó).

    def _seen_key(self, episode_id: UUID) -> str:
        return f"{SEEN_KEY_PREFIX}{episode_id}"

    async def get_seen_seq(self, episode_id: UUID, idempotency_key: str) -> int | None:
        """Devuelve el seq registrado para este `idempotency_key`, o None.

        Primitiva de lectura de bajo nivel. El flujo de dedup vivo es
        `reserve_or_get_seq` (atómico); esta se conserva para inspección/tests.
        """
        raw = await self.redis.hget(self._seen_key(episode_id), idempotency_key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            # Valor corrupto: tratamos como no-visto (fail-safe hacia emitir).
            return None

    async def mark_seen(self, episode_id: UUID, idempotency_key: str, seq: int) -> None:
        """Registra `idempotency_key -> seq` para el episodio con TTL acotado.

        Se llama DESPUÉS de asignar el seq y publicar el evento, para que un
        reintento posterior del mismo `event_uuid` de cliente recupere el seq
        ya asignado en vez de avanzar el contador de sesión.
        """
        key = self._seen_key(episode_id)
        await self.redis.hset(key, idempotency_key, str(seq))
        await self.redis.expire(key, SEEN_TTL)

    async def clear_seen(self, episode_id: UUID) -> None:
        """Borra el registro de idempotencia del episodio (cierre/expiración)."""
        await self.redis.delete(self._seen_key(episode_id))

    async def iter_active_sessions(self) -> AsyncIterator[SessionState]:
        """Itera todas las sesiones activas en Redis (ADR-025).

        Usado por el worker de abandono para detectar sesiones inactivas.
        Tolera state corruptos (los skipea con log).

        Devuelve un async-iterator de SessionState — el caller decide que
        hacer con cada una segun el `last_activity_at`.
        """
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match=f"{SESSION_KEY_PREFIX}*",
                count=100,
            )
            for key in keys:
                # Extraer episode_id del key (decode si es bytes)
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                episode_id_str = key_str[len(SESSION_KEY_PREFIX) :]
                try:
                    episode_id = UUID(episode_id_str)
                except ValueError:
                    continue  # key con formato invalido, skip
                state = await self.get(episode_id)
                if state is not None:
                    yield state
            if cursor == 0:
                break

    # ── Distraction tracking ────────────────────────────────────────────

    def _distraction_key(self, episode_id: UUID) -> str:
        return f"{DISTRACTION_KEY_PREFIX}{episode_id}"

    async def mark_distraction(self, episode_id: UUID, started_at: float) -> None:
        """Guarda el timestamp en que el alumno perdió foco de la pestaña."""
        await self.redis.setex(
            self._distraction_key(episode_id),
            DISTRACTION_TTL,
            str(started_at),
        )

    async def clear_distraction(self, episode_id: UUID) -> None:
        """Borra la marca de distracción (alumno volvió a la pestaña)."""
        await self.redis.delete(self._distraction_key(episode_id))

    async def iter_distractions(self) -> AsyncIterator[tuple[UUID, float]]:
        """Itera (episode_id, started_at) de todas las distracciones activas."""
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor=cursor,
                match=f"{DISTRACTION_KEY_PREFIX}*",
                count=100,
            )
            for key in keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                episode_id_str = key_str[len(DISTRACTION_KEY_PREFIX) :]
                try:
                    episode_id = UUID(episode_id_str)
                except ValueError:
                    continue
                raw = await self.redis.get(self._distraction_key(episode_id))
                if raw is None:
                    continue
                try:
                    started_at = float(raw)
                except (TypeError, ValueError):
                    continue
                yield (episode_id, started_at)
            if cursor == 0:
                break
