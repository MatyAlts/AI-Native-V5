"""Session manager del tutor.

El tutor mantiene una sesión por episodio con:
- seq actual (próximo evento a publicar)
- mensajes previos de la conversación (para contexto multi-turno)

Estado en Redis con TTL de 6h (las sesiones típicas duran <1h). Al
cerrar episodio o al expirar, el state se elimina; la fuente de verdad
histórica es el CTR en Postgres.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

import redis.asyncio as redis

SESSION_TTL = 6 * 3600  # 6 horas

# ADR-025 (G10-A): clave bajo la cual se almacenan las sesiones del tutor.
# El worker de abandono escanea con MATCH sobre este prefijo + "*".
SESSION_KEY_PREFIX = "tutor:session:"


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
        }
        await self.redis.setex(self._key(state.episode_id), SESSION_TTL, json.dumps(data))

    async def delete(self, episode_id: UUID) -> None:
        await self.redis.delete(self._key(episode_id))

    async def next_seq(self, state: SessionState) -> int:
        """Obtiene y actualiza el seq atómicamente. Devuelve el seq a usar
        para el próximo evento (el siguiente será seq+1)."""
        current = state.seq
        state.seq += 1
        await self.set(state)
        return current

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
