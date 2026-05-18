"""Adaptador DB real para exportación académica + análisis longitudinal.

Reemplaza los `_StubDataSource` de F7 con queries reales que respetan
la arquitectura de 3 bases lógicas:

  - **ctr_store**: episodes + events (con RLS por tenant)
  - **classifier_db**: classifications (con RLS por tenant)

Ambas DBs se acceden con **sesiones separadas** (ADR-005). El adaptador
abre dos sesiones, una por DB, y las coordina. RLS se activa seteando
`SET LOCAL app.current_tenant` al inicio de cada transacción.

Uso:
    async with get_ctr_session() as ctr_s, get_classifier_session() as cls_s:
        ds = RealDataSource(
            ctr_session=ctr_s,
            classifier_session=cls_s,
            tenant_id=tenant_id,
        )
        dataset = await exporter.export_cohort(...)

Los tests de este módulo usan SQLite in-memory (sin RLS real, pero
suficiente para verificar la lógica de joins y filtros).
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RealCohortDataSource:
    """DataSource real que implementa la interface del AcademicExporter.

    Requiere dos sesiones (ctr_store + classifier_db) ya con el RLS
    aplicado vía `SET LOCAL app.current_tenant = '<uuid>'`.
    """

    def __init__(
        self,
        ctr_session: AsyncSession,
        classifier_session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self.ctr = ctr_session
        self.classifier = classifier_session
        self.tenant_id = tenant_id

    async def list_episodes_in_comision(self, comision_id: UUID, since: datetime) -> list[dict]:
        """Lista episodios de la comisión abiertos desde `since`.

        RLS filtra automáticamente por tenant; el WHERE doble es
        defensivo (patrón recomendado en ADR-007).
        """
        # Import late para evitar ciclos en testing
        from ctr_service.models import Episode

        stmt = (
            select(Episode)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == self.tenant_id)  # doble filtro
            .where(Episode.opened_at >= since)
            .order_by(Episode.opened_at.asc())
        )
        result = await self.ctr.execute(stmt)
        episodes = result.scalars().all()
        return [
            {
                "id": ep.id,
                "comision_id": ep.comision_id,
                "student_pseudonym": ep.student_pseudonym,
                "problema_id": getattr(ep, "problema_id", None),
                "opened_at": ep.opened_at,
            }
            for ep in episodes
        ]

    async def list_events_for_episode(self, episode_id: UUID) -> list[dict]:
        """Lista los eventos de un episodio, ordenados por seq."""
        from ctr_service.models import Event

        stmt = (
            select(Event)
            .where(Event.episode_id == episode_id)
            .where(Event.tenant_id == self.tenant_id)  # doble filtro
            .order_by(Event.seq.asc())
        )
        result = await self.ctr.execute(stmt)
        events = result.scalars().all()
        return [
            {
                "seq": ev.seq,
                "event_type": ev.event_type,
                "ts": ev.ts.isoformat().replace("+00:00", "Z") if ev.ts else None,
                "payload": ev.payload or {},
            }
            for ev in events
        ]

    async def get_current_classification(self, episode_id: UUID) -> dict | None:
        """Obtiene la clasificación actual (`is_current=true`) de un episodio."""
        from classifier_service.models import Classification

        stmt = (
            select(Classification)
            .where(Classification.episode_id == episode_id)
            .where(Classification.tenant_id == self.tenant_id)
            .where(Classification.is_current.is_(True))
            .order_by(Classification.classified_at.desc())
            .limit(1)
        )
        result = await self.classifier.execute(stmt)
        c = result.scalar_one_or_none()
        if c is None:
            return None
        return {
            "appropriation": c.appropriation,
            "appropiation": c.appropriation,  # compat con academic_export.py
            "classifier_config_hash": c.classifier_config_hash,
            "ct_summary": c.ct_summary,
            "ccd_mean": c.ccd_mean,
            "ccd_orphan_ratio": c.ccd_orphan_ratio,
            "cii_stability": c.cii_stability,
            "cii_evolution": c.cii_evolution,
        }


class RealLongitudinalDataSource:
    """DataSource real para análisis longitudinal.

    La query clave cruza episodes (para obtener student_pseudonym) con
    classifications (para las etiquetas) y agrupa por estudiante.
    """

    def __init__(
        self,
        ctr_session: AsyncSession,
        classifier_session: AsyncSession,
        tenant_id: UUID,
        pseudonymize_fn=None,
    ) -> None:
        self.ctr = ctr_session
        self.classifier = classifier_session
        self.tenant_id = tenant_id
        # Si se provee, las filas se anonimizan (útil para endpoint público)
        self.pseudonymize_fn = pseudonymize_fn

    async def list_classifications_grouped_by_student(
        self, comision_id: UUID
    ) -> dict[str, list[dict]]:
        """Devuelve {student_pseudonym: [classification_dict, ...]}.

        Cuando el caller pasa `pseudonymize_fn`, la key del dict puede ser
        un alias anonimizado en vez del pseudonym crudo — uso reservado a
        export académico (`academic_export.py`). En el flujo de UI interna
        (progression, adversarial-events) `pseudonymize_fn=None` y la key
        es el `str(student_pseudonym)` directo.

        La agrupación por estudiante se hace en Python en vez de SQL
        porque las dos tablas viven en DBs distintas (3-base pattern).
        Esto es OK para cohortes del piloto (<500 episodios).
        """
        from classifier_service.models import Classification
        from ctr_service.models import Episode

        # 1. Traer episodios de la comisión para resolver episode_id →
        #    student_pseudonym.
        ep_stmt = (
            select(Episode.id, Episode.student_pseudonym)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == self.tenant_id)
        )
        ep_result = await self.ctr.execute(ep_stmt)
        ep_to_student: dict[UUID, UUID] = {row.id: row.student_pseudonym for row in ep_result.all()}
        if not ep_to_student:
            return {}

        # 2. Traer clasificaciones current de esos episodios
        cls_stmt = (
            select(Classification)
            .where(Classification.comision_id == comision_id)
            .where(Classification.tenant_id == self.tenant_id)
            .where(Classification.is_current.is_(True))
            .where(Classification.episode_id.in_(ep_to_student.keys()))
            .order_by(Classification.classified_at.asc())
        )
        cls_result = await self.classifier.execute(cls_stmt)

        # 3. Agrupar por estudiante
        grouped: dict[str, list[dict]] = {}
        for c in cls_result.scalars().all():
            student_pseudo = ep_to_student.get(c.episode_id)
            if student_pseudo is None:
                continue  # episodio de otra comisión (shouldn't happen con RLS)

            alias = (
                self.pseudonymize_fn(student_pseudo)
                if self.pseudonymize_fn
                else str(student_pseudo)
            )
            grouped.setdefault(alias, []).append(
                {
                    "episode_id": c.episode_id,
                    "classified_at": c.classified_at,
                    "appropriation": c.appropriation,
                    "ct_summary": c.ct_summary,
                    "ccd_mean": c.ccd_mean,
                    "ccd_orphan_ratio": c.ccd_orphan_ratio,
                    "cii_stability": c.cii_stability,
                    "cii_evolution": c.cii_evolution,
                }
            )

        return grouped

    async def list_adversarial_events_by_comision(
        self,
        comision_id: UUID,
        limit_recent: int = 50,
    ) -> list[dict]:
        """ADR-019: lista eventos `intento_adverso_detectado` de una comisión.

        Cross-DB CTR: cruza `Event` (event_type='intento_adverso_detectado')
        con `Episode` (para obtener `student_pseudonym` + `comision_id`).
        Devuelve lista plana de dicts; el caller agrega contadores.
        """
        from ctr_service.models import Episode, Event

        # 1. Episodios de la comision para resolver episode_id → student
        ep_stmt = (
            select(Episode.id, Episode.student_pseudonym)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == self.tenant_id)
        )
        ep_result = await self.ctr.execute(ep_stmt)
        ep_to_student: dict[UUID, UUID] = {row.id: row.student_pseudonym for row in ep_result.all()}
        if not ep_to_student:
            return []

        # 2. Eventos adversos de esos episodios
        ev_stmt = (
            select(Event)
            .where(Event.event_type == "intento_adverso_detectado")
            .where(Event.tenant_id == self.tenant_id)
            .where(Event.episode_id.in_(ep_to_student.keys()))
            .order_by(Event.ts.desc())
        )
        ev_result = await self.ctr.execute(ev_stmt)

        out: list[dict] = []
        for ev in ev_result.scalars().all():
            student_pseudo = ep_to_student.get(ev.episode_id)
            if student_pseudo is None:
                continue
            student_id = (
                self.pseudonymize_fn(student_pseudo)
                if self.pseudonymize_fn
                else str(student_pseudo)
            )
            payload = ev.payload or {}
            out.append(
                {
                    "episode_id": str(ev.episode_id),
                    "student_pseudonym": student_id,
                    "ts": ev.ts.isoformat().replace("+00:00", "Z") if ev.ts else None,
                    "category": payload.get("category", "unknown"),
                    "severity": int(payload.get("severity", 0)),
                    "pattern_id": payload.get("pattern_id", ""),
                    "matched_text": payload.get("matched_text", ""),
                    "guardrails_corpus_hash": payload.get("guardrails_corpus_hash", ""),
                }
            )

        return out[:limit_recent] if limit_recent else out

    async def list_episodes_with_classifications_for_student(
        self,
        student_pseudonym: UUID,
        comision_id: UUID,
        academic_session: AsyncSession,
    ) -> list[dict]:
        """ADR-018 + drill-down: lista de episodios CERRADOS del estudiante con
        classification + template_id. Pensado para que el frontend muestre un
        dropdown "selectable" en vez de pedir UUIDs pegados.

        Triple cross-DB ctr + classifier + academic. Ordenado por
        `closed_at` desc (más recientes primero — UX típico).
        """
        from academic_service.models.operacional import TareaPractica
        from classifier_service.models import Classification
        from ctr_service.models import Episode

        ep_stmt = (
            select(
                Episode.id,
                Episode.problema_id,
                Episode.opened_at,
                Episode.closed_at,
                Episode.estado,
                Episode.events_count,
            )
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == self.tenant_id)
            .where(Episode.student_pseudonym == student_pseudonym)
            .where(Episode.estado == "closed")
            .order_by(Episode.closed_at.desc())
        )
        ep_result = await self.ctr.execute(ep_stmt)
        episodes_raw = ep_result.all()
        if not episodes_raw:
            return []

        ep_ids = [row.id for row in episodes_raw]
        problema_ids = list({row.problema_id for row in episodes_raw})

        # Templates (por TP)
        tp_stmt = (
            select(
                TareaPractica.id,
                TareaPractica.template_id,
                TareaPractica.codigo,
                TareaPractica.titulo,
            )
            .where(TareaPractica.id.in_(problema_ids))
            .where(TareaPractica.tenant_id == self.tenant_id)
        )
        tp_result = await academic_session.execute(tp_stmt)
        tp_by_id: dict[UUID, dict] = {
            row.id: {"template_id": row.template_id, "codigo": row.codigo, "titulo": row.titulo}
            for row in tp_result.all()
        }

        # Classifications current
        cls_stmt = (
            select(Classification)
            .where(Classification.episode_id.in_(ep_ids))
            .where(Classification.tenant_id == self.tenant_id)
            .where(Classification.is_current.is_(True))
        )
        cls_result = await self.classifier.execute(cls_stmt)
        cls_by_episode: dict[UUID, dict] = {
            c.episode_id: {
                "appropriation": c.appropriation,
                "classified_at": c.classified_at,
            }
            for c in cls_result.scalars().all()
        }

        out: list[dict] = []
        for row in episodes_raw:
            tp = tp_by_id.get(row.problema_id, {})
            cls = cls_by_episode.get(row.id)
            out.append(
                {
                    "episode_id": str(row.id),
                    "problema_id": str(row.problema_id),
                    "tarea_codigo": tp.get("codigo"),
                    "tarea_titulo": tp.get("titulo"),
                    "template_id": str(tp["template_id"]) if tp.get("template_id") else None,
                    "opened_at": row.opened_at.isoformat().replace("+00:00", "Z")
                    if row.opened_at
                    else None,
                    "closed_at": row.closed_at.isoformat().replace("+00:00", "Z")
                    if row.closed_at
                    else None,
                    "events_count": row.events_count,
                    "appropriation": cls["appropriation"] if cls else None,
                    "classified_at": (
                        cls["classified_at"].isoformat().replace("+00:00", "Z")
                        if cls and cls["classified_at"]
                        else None
                    ),
                }
            )
        return out

    async def list_classifications_with_templates_for_student(
        self,
        student_pseudonym: UUID,
        comision_id: UUID,
        academic_session: AsyncSession,
    ) -> list[dict]:
        """ADR-018: devuelve clasificaciones de UN estudiante en una comision,
        cada una con `template_id` resuelto vía academic_main.

        Triple cross-DB: ctr (Episode) + classifier (Classification) +
        academic (TareaPractica.template_id). Cada query con su propia
        sesion (RLS aplicado por el caller).

        Devuelve lista plana de dicts; el caller agrupa por template_id
        via `compute_evolution_per_template`.
        """
        # Late imports para evitar ciclos en testing
        from academic_service.models.operacional import TareaPractica
        from classifier_service.models import Classification
        from ctr_service.models import Episode

        # 1. Episodios del estudiante en la comision
        ep_stmt = (
            select(Episode.id, Episode.problema_id)
            .where(Episode.comision_id == comision_id)
            .where(Episode.tenant_id == self.tenant_id)
            .where(Episode.student_pseudonym == student_pseudonym)
        )
        ep_result = await self.ctr.execute(ep_stmt)
        ep_to_problema: dict[UUID, UUID] = {row.id: row.problema_id for row in ep_result.all()}
        if not ep_to_problema:
            return []

        # 2. Resolver problema_id → template_id + unidad_id via academic_main
        problema_ids = list(set(ep_to_problema.values()))
        tp_stmt = (
            select(TareaPractica.id, TareaPractica.template_id, TareaPractica.unidad_id)
            .where(TareaPractica.id.in_(problema_ids))
            .where(TareaPractica.tenant_id == self.tenant_id)
        )
        tp_result = await academic_session.execute(tp_stmt)
        tp_data: dict[UUID, dict] = {
            row.id: {"template_id": row.template_id, "unidad_id": row.unidad_id}
            for row in tp_result.all()
        }

        # 3. Classifications current de esos episodios
        cls_stmt = (
            select(Classification)
            .where(Classification.comision_id == comision_id)
            .where(Classification.tenant_id == self.tenant_id)
            .where(Classification.is_current.is_(True))
            .where(Classification.episode_id.in_(ep_to_problema.keys()))
            .order_by(Classification.classified_at.asc())
        )
        cls_result = await self.classifier.execute(cls_stmt)

        # 4. Construir lista con template_id + unidad_id resueltos
        out: list[dict] = []
        for c in cls_result.scalars().all():
            problema_id = ep_to_problema.get(c.episode_id)
            tp = tp_data.get(problema_id, {}) if problema_id else {}
            out.append(
                {
                    "episode_id": c.episode_id,
                    "problema_id": problema_id,
                    "template_id": tp.get("template_id"),  # None si TP huerfana → skipped downstream
                    "unidad_id": tp.get("unidad_id"),  # None si sin unidad → "sin_unidad" downstream
                    "classified_at": c.classified_at,
                    "appropriation": c.appropriation,
                }
            )

        return out

    async def list_unidades_by_ids(
        self,
        unidad_ids: list[UUID],
        academic_session: AsyncSession,
    ) -> dict[str, dict]:
        """Resuelve unidad_id → {nombre} via academic_main.

        Devuelve dict keyed by str(unidad_id) para alinear con el sentinel
        "sin_unidad" que usa compute_evolution_per_unidad.

        Guard: si la lista esta vacia devuelve {} sin ejecutar query
        (evita IN clause vacia que falla en Postgres).
        """
        if not unidad_ids:
            return {}

        from academic_service.models.operacional import Unidad

        stmt = (
            select(Unidad.id, Unidad.nombre)
            .where(Unidad.id.in_(unidad_ids))
            .where(Unidad.tenant_id == self.tenant_id)
            .where(Unidad.deleted_at.is_(None))
        )
        result = await academic_session.execute(stmt)
        return {str(row.id): {"nombre": row.nombre} for row in result.all()}


# ── Helper para setear RLS ────────────────────────────────────────────


async def set_tenant_rls(session: AsyncSession, tenant_id: UUID) -> None:
    """Setea el tenant_id para que RLS filtre automáticamente.

    Debe llamarse al inicio de cada transacción. SET LOCAL dura solo
    hasta el final de la transacción actual — por eso rollbacks + new
    txn necesitan re-setearlo.
    """
    from sqlalchemy import text

    # SET LOCAL no admite bind parameters (Postgres utility statement).
    # Interpolamos literal: tenant_id es UUID validado por type hint,
    # no puede contener comillas ni caracteres que inyecten SQL.
    await session.execute(text(f"SET LOCAL app.current_tenant = '{tenant_id}'"))


__all__ = [
    "RealCohortDataSource",
    "RealLongitudinalDataSource",
    "set_tenant_rls",
]
