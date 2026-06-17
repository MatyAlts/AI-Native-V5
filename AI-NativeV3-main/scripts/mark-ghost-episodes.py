#!/usr/bin/env python3
"""Limpieza retroactiva de episodios "fantasma" (ghost resume duplicates).

Un bug hacia que, al reabrir un ejercicio sin cerrar, se creara un episodio
NUEVO en vez de reanudar el existente. Resultado: episodios ``paused`` sin
clasificar que son intentos redundantes de un ejercicio que el alumno SI
completo (y clasifico) en otra sesion. Este script los MARCA como
``superseded`` en ``Episode.meta`` para que no ensucien el "conteo de
sesiones" del drill-down docente, SIN borrarlos (append-only ADR-010).

Regla de "fantasma" (las TRES condiciones, ver platform_ops.ghost_episodes):
    1. estado == "paused", y
    2. NO tiene Classification is_current (no clasificado), y
    3. existe OTRO episodio del mismo (tenant, student, problema, ejercicio)
       que SI tiene Classification is_current.

Que escribe (metadata mutable, NO viola append-only):
    meta['superseded']        = True
    meta['superseded_by']     = episode_id del episodio clasificado "bueno"
    meta['superseded_reason'] = "ghost_resume_duplicate"
    meta['superseded_at']     = timestamp ISO (UTC)

NUNCA toca la tabla `events`, ni hashes, ni borra nada. Solo UPDATE de
`Episode.meta`.

Resolucion del ejercicio_id:
    Primero `Episode.meta['ejercicio_id']`; si no esta, el payload del primer
    evento `episodio_abierto` (seq=0) en `events`. Episodios legacy sin
    ejercicio_id en ningun lado quedan con ejercicio_id=None (agrupan por
    (student, problema) — siguen siendo agrupables).

Env vars (mismo patron que otros scripts del repo):
    CTR_STORE_URL        — ctr_store (episodes + events)
    CLASSIFIER_DB_URL    — classifier_db (classifications)

Uso:
    # Dry-run (DEFECTO): imprime lo que marcaria, NO escribe.
    python scripts/mark-ghost-episodes.py

    # Aplicar de verdad (UPDATE de meta en transaccion, idempotente).
    python scripts/mark-ghost-episodes.py --apply

    # Acotar a una comision.
    python scripts/mark-ghost-episodes.py --comision <uuid>

Idempotencia:
    Re-correr es SEGURO. Episodios ya marcados (meta['superseded']==True) se
    saltean. No-op en la segunda corrida.

Stdout en ASCII (sin tildes ni emojis — convencion del repo, cp1252 de
Windows rompe; ver check-rls.py).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Imports de los modelos de los servicios (mismo patron que otros scripts).
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "apps" / "ctr-service" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "classifier-service" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "platform-ops" / "src"))

from platform_ops.ghost_episodes import (
    EpisodeInfo,
    GhostMark,
    build_superseded_meta,
    select_ghost_episodes,
)


def _redact(url: str) -> str:
    """Oculta el password del DB URL para logging seguro."""
    if "@" not in url:
        return url
    prefix, rest = url.split("@", 1)
    if "://" in prefix and ":" in prefix.split("://", 1)[1]:
        scheme, userpass = prefix.split("://", 1)
        user = userpass.split(":", 1)[0]
        return f"{scheme}://{user}:***@{rest}"
    return url


async def _load_episode_infos(
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    comision_id: UUID | None,
) -> list[EpisodeInfo]:
    """Construye los EpisodeInfo desde CTR + classifier_db.

    Resuelve ejercicio_id (meta -> evento episodio_abierto) y marca cuales
    estan clasificados (Classification is_current). Read-only.
    """
    from ctr_service.models import Episode, Event

    # 1. Episodios (no filtramos por estado: necesitamos los clasificados
    # de cualquier estado para evaluar la condicion 3 del grupo).
    ep_stmt = select(
        Episode.id,
        Episode.student_pseudonym,
        Episode.problema_id,
        Episode.estado,
        Episode.opened_at,
        Episode.events_count,
        Episode.meta,
    )
    if comision_id is not None:
        ep_stmt = ep_stmt.where(Episode.comision_id == comision_id)
    ep_rows = (await ctr_session.execute(ep_stmt)).all()
    if not ep_rows:
        return []

    ep_ids = [row.id for row in ep_rows]

    # 2. ejercicio_id desde el evento episodio_abierto (seq=0) para los
    # episodios cuyo meta no lo tiene. Una sola query batch.
    needs_event_lookup = [
        row.id for row in ep_rows if not (row.meta or {}).get("ejercicio_id")
    ]
    ejercicio_by_event: dict[UUID, str | None] = {}
    if needs_event_lookup:
        ev_stmt = (
            select(Event.episode_id, Event.payload)
            .where(Event.episode_id.in_(needs_event_lookup))
            .where(Event.event_type == "episodio_abierto")
        )
        for ev_row in (await ctr_session.execute(ev_stmt)).all():
            payload = ev_row.payload or {}
            ejercicio_by_event[ev_row.episode_id] = payload.get("ejercicio_id")

    # 3. Episodios clasificados (Classification is_current).
    from classifier_service.models import Classification

    cls_stmt = (
        select(Classification.episode_id)
        .where(Classification.episode_id.in_(ep_ids))
        .where(Classification.is_current.is_(True))
    )
    classified_ids = {
        row.episode_id for row in (await classifier_session.execute(cls_stmt)).all()
    }

    infos: list[EpisodeInfo] = []
    for row in ep_rows:
        meta = row.meta or {}
        raw_ejercicio = meta.get("ejercicio_id") or ejercicio_by_event.get(row.id)
        ejercicio_id: UUID | None = None
        if raw_ejercicio:
            try:
                ejercicio_id = UUID(str(raw_ejercicio))
            except (ValueError, AttributeError, TypeError):
                ejercicio_id = None

        infos.append(
            EpisodeInfo(
                episode_id=row.id,
                student_pseudonym=row.student_pseudonym,
                problema_id=row.problema_id,
                ejercicio_id=ejercicio_id,
                estado=row.estado,
                is_classified=row.id in classified_ids,
                opened_at=row.opened_at,
                events_count=row.events_count or 0,
                meta=meta,
            )
        )
    return infos


def _print_dry_run(marks: list[GhostMark]) -> None:
    """Imprime la lista agrupada por alumno (ASCII)."""
    by_student: dict[UUID, list[GhostMark]] = defaultdict(list)
    for m in marks:
        by_student[m.student_pseudonym].append(m)

    print()
    print("Episodios fantasma que se marcarian (agrupados por alumno):")
    print("=" * 70)
    for student, student_marks in by_student.items():
        print(f"\nAlumno {student} ({len(student_marks)} episodios):")
        for m in sorted(student_marks, key=lambda x: str(x.opened_at)):
            opened = m.opened_at.isoformat() if m.opened_at else "?"
            ej = str(m.ejercicio_id) if m.ejercicio_id else "(sin ejercicio_id)"
            print(
                f"  problema={m.problema_id} ejercicio={ej}\n"
                f"    episode_id={m.episode_id} events={m.events_count} "
                f"opened_at={opened}\n"
                f"    -> superseded_by={m.superseded_by}"
            )


async def _apply_marks(
    ctr_session: AsyncSession,
    infos_by_id: dict[UUID, EpisodeInfo],
    marks: list[GhostMark],
    superseded_at: str,
) -> tuple[int, int]:
    """Aplica los UPDATE de meta en transaccion. Devuelve (marcados, ya_estaban).

    Idempotente: si el episodio ya esta superseded, se saltea (no cuenta como
    marcado). El re-check usa el meta cargado en infos (consistente con la
    funcion pura, que ya filtra los superseded del resultado).
    """
    from ctr_service.models import Episode

    n_marked = 0
    n_skipped = 0
    for m in marks:
        info = infos_by_id[m.episode_id]
        if info.meta.get("superseded") is True:
            n_skipped += 1
            continue
        new_meta = build_superseded_meta(
            current_meta=info.meta,
            superseded_by=m.superseded_by,
            superseded_at=superseded_at,
        )
        await ctr_session.execute(
            update(Episode).where(Episode.id == m.episode_id).values(meta=new_meta)
        )
        n_marked += 1

    await ctr_session.commit()
    return n_marked, n_skipped


async def main(apply: bool, comision_id: UUID | None) -> int:
    ctr_url = os.environ.get(
        "CTR_STORE_URL",
        "postgresql+asyncpg://ctr_user:ctr_pass@localhost:5432/ctr_store",
    )
    classifier_url = os.environ.get(
        "CLASSIFIER_DB_URL",
        "postgresql+asyncpg://classifier_user:classifier_pass@localhost:5432/classifier_db",
    )

    print(f"CTR_STORE_URL     = {_redact(ctr_url)}")
    print(f"CLASSIFIER_DB_URL = {_redact(classifier_url)}")
    print(f"Comision          = {comision_id if comision_id else '(todas)'}")
    print(f"Modo              = {'APPLY (escribe meta)' if apply else 'DRY-RUN (no escribe)'}")

    ctr_engine = create_async_engine(ctr_url, pool_size=2)
    classifier_engine = create_async_engine(classifier_url, pool_size=2)
    ctr_maker = async_sessionmaker(ctr_engine, expire_on_commit=False)
    classifier_maker = async_sessionmaker(classifier_engine, expire_on_commit=False)

    try:
        async with ctr_maker() as ctr_s, classifier_maker() as cls_s:
            infos = await _load_episode_infos(ctr_s, cls_s, comision_id)
            print(f"\nEpisodios analizados: {len(infos)}")

            marks = select_ghost_episodes(infos)
            students = {m.student_pseudonym for m in marks}

            if not marks:
                print("\n[OK] No hay episodios fantasma para marcar. Salida limpia.")
                return 0

            _print_dry_run(marks)

            print()
            print("=" * 70)
            if not apply:
                print(
                    f"DRY-RUN: marcaria {len(marks)} episodios de {len(students)} alumnos."
                )
                print("Para aplicar de verdad, correr con --apply.")
                return 0

            infos_by_id = {info.episode_id: info for info in infos}
            superseded_at = datetime.now(UTC).isoformat()
            n_marked, n_skipped = await _apply_marks(
                ctr_s, infos_by_id, marks, superseded_at
            )
            print(
                f"APPLY: {n_marked} marcados / {n_skipped} ya estaban / "
                f"{len(students)} alumnos."
            )
            return 0
    finally:
        await ctr_engine.dispose()
        await classifier_engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Marca episodios fantasma (ghost resume duplicates) como superseded en Episode.meta."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica los UPDATE de meta. Sin esta flag corre en dry-run (no escribe).",
    )
    parser.add_argument(
        "--comision",
        type=str,
        default=None,
        help="UUID de comision para acotar (opcional).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    comision = UUID(args.comision) if args.comision else None
    sys.exit(asyncio.run(main(apply=args.apply, comision_id=comision)))
