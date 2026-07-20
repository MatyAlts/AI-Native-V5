"""Logica pura para detectar episodios "fantasma" (ghost) y marcarlos.

Contexto del bug
----------------
Un bug hacia que, al reabrir un ejercicio sin cerrar, se creara un episodio
NUEVO en vez de reanudar el existente. Resultado: episodios "fantasma" en
estado ``paused``, sin clasificar, que son intentos redundantes de un
ejercicio que el alumno SI completo (y clasifico) en otra sesion.

Estos episodios ensucian el "conteo de sesiones" del drill-down docente.
No se borran (append-only ADR-010): se MARCAN como ``superseded`` escribiendo
en ``Episode.meta`` (metadata mutable, NO viola append-only — la tabla
``events`` ni los hashes se tocan).

Regla de "fantasma" (las TRES condiciones)
-------------------------------------------
Un episodio se marca como descartado SOLO si cumple las tres:

1. ``estado == "paused"``, y
2. NO tiene ``Classification`` con ``is_current = true`` (no esta clasificado), y
3. existe OTRO episodio del mismo grupo
   ``(tenant_id, student_pseudonym, problema_id, ejercicio_id)`` que SI tiene
   una ``Classification is_current`` (el alumno completo ese ejercicio en otra
   sesion).

Esta capa es DB-agnostica: recibe descriptores planos de episodios y devuelve
las decisiones de marcado. El IO (queries, UPDATE de meta) vive en
``scripts/mark-ghost-episodes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

# Constantes del marcado (la fuente de verdad de las claves de meta).
SUPERSEDED_KEY = "superseded"
SUPERSEDED_BY_KEY = "superseded_by"
SUPERSEDED_REASON_KEY = "superseded_reason"
SUPERSEDED_AT_KEY = "superseded_at"

GHOST_RESUME_REASON = "ghost_resume_duplicate"

# Estado de un episodio fantasma candidato.
PAUSED_STATE = "paused"


@dataclass(frozen=True)
class EpisodeInfo:
    """Descriptor plano de un episodio para la decision de marcado.

    No depende de SQLAlchemy: el caller lo construye desde el row de la DB.
    """

    episode_id: UUID
    student_pseudonym: UUID
    problema_id: UUID
    ejercicio_id: UUID | None
    estado: str
    is_classified: bool
    opened_at: datetime | None = None
    events_count: int = 0
    # ``meta`` actual del episodio — usado para detectar idempotencia
    # (si ya tiene ``superseded == True`` se saltea, no se re-marca).
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GhostMark:
    """Decision de marcar un episodio como fantasma."""

    episode_id: UUID
    student_pseudonym: UUID
    problema_id: UUID
    ejercicio_id: UUID | None
    superseded_by: UUID
    opened_at: datetime | None
    events_count: int


def _group_key(ep: EpisodeInfo) -> tuple[UUID, UUID, UUID | None]:
    """Clave de agrupamiento por (student, problema, ejercicio).

    El ``tenant_id`` NO entra en la clave porque el caller ya acota la query
    a un unico tenant via RLS (la lista de entrada es siempre mono-tenant).
    """
    return (ep.student_pseudonym, ep.problema_id, ep.ejercicio_id)


def _already_superseded(ep: EpisodeInfo) -> bool:
    """True si el episodio ya esta marcado (idempotencia)."""
    return bool(ep.meta.get(SUPERSEDED_KEY) is True)


def select_ghost_episodes(episodes: list[EpisodeInfo]) -> list[GhostMark]:
    """Funcion pura: decide que episodios marcar como fantasma.

    Agrupa los episodios por ``(student_pseudonym, problema_id, ejercicio_id)``
    y, dentro de cada grupo, marca los ``paused`` no-clasificados SI existe al
    menos otro episodio clasificado (``is_current``) en el mismo grupo.

    Idempotente: episodios que ya tienen ``meta['superseded'] == True`` NO se
    re-marcan (se omiten del resultado).

    El "bueno" elegido como ``superseded_by`` es deterministico: el episodio
    clasificado del grupo con menor ``episode_id`` (estable entre corridas).
    """
    groups: dict[tuple[UUID, UUID, UUID | None], list[EpisodeInfo]] = {}
    for ep in episodes:
        groups.setdefault(_group_key(ep), []).append(ep)

    marks: list[GhostMark] = []
    for group in groups.values():
        classified = [ep for ep in group if ep.is_classified]
        if not classified:
            # Condicion 3 no se cumple: nadie completo el ejercicio.
            continue

        # El "bueno" canonico: clasificado con menor episode_id (deterministico).
        good = min(classified, key=lambda e: str(e.episode_id))

        for ep in group:
            # Condicion 1: paused.
            if ep.estado != PAUSED_STATE:
                continue
            # Condicion 2: no clasificado.
            if ep.is_classified:
                continue
            # Idempotencia: ya marcado.
            if _already_superseded(ep):
                continue
            # No marcar el episodio "bueno" contra si mismo (defensivo:
            # el bueno esta clasificado, ya filtrado arriba, pero por las dudas).
            if ep.episode_id == good.episode_id:
                continue

            marks.append(
                GhostMark(
                    episode_id=ep.episode_id,
                    student_pseudonym=ep.student_pseudonym,
                    problema_id=ep.problema_id,
                    ejercicio_id=ep.ejercicio_id,
                    superseded_by=good.episode_id,
                    opened_at=ep.opened_at,
                    events_count=ep.events_count,
                )
            )

    return marks


def build_superseded_meta(
    current_meta: dict[str, Any] | None,
    superseded_by: UUID,
    superseded_at: str,
    reason: str = GHOST_RESUME_REASON,
) -> dict[str, Any]:
    """Devuelve un meta NUEVO con las claves de superseded agregadas.

    No muta ``current_meta``. ``superseded_at`` se pasa como string ISO
    (parametro inyectado — la logica pura no usa ``datetime.now()``).
    """
    new_meta = dict(current_meta or {})
    new_meta[SUPERSEDED_KEY] = True
    new_meta[SUPERSEDED_BY_KEY] = str(superseded_by)
    new_meta[SUPERSEDED_REASON_KEY] = reason
    new_meta[SUPERSEDED_AT_KEY] = superseded_at
    return new_meta
