"""Batch de clasificaciones-con-templates para TODA una cohorte (P-4).

Los endpoints de alertas (`/student/{id}/alerts` y `/cohort/{id}/alerts-summary`)
necesitan el `mean_slope` longitudinal de cada estudiante de la comisión para
armar la distribución de cohorte (cuartiles + z-score). La implementación
original iteraba por estudiante llamando
`RealLongitudinalDataSource.list_classifications_with_templates_for_student`
una vez por alumno — 3 queries cross-DB × N alumnos (N+1 clásico).

Este módulo hace lo mismo en **una sola pasada**: 3 queries totales
(episodes + tareas_practicas + classifications) para toda la cohorte, y agrupa
por estudiante en Python. El resultado por estudiante es **idéntico** al de la
función per-alumno (mismos filtros, misma forma de dict, mismo orden por
`classified_at`), así que `compute_cii_evolution_longitudinal` devuelve el
mismo slope.

RLS: las 3 sesiones (ctr/classifier/academic) las abre y setea el caller vía
`set_tenant_rls` — este helper no toca RLS, solo consulta.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def batch_classifications_with_templates_by_student(
    *,
    ctr_session: AsyncSession,
    classifier_session: AsyncSession,
    academic_session: AsyncSession,
    comision_id: UUID,
    tenant_id: UUID,
    language: str | None = None,
) -> dict[UUID, list[dict[str, Any]]]:
    """Devuelve {student_pseudonym: [classification_dict, ...]} para la cohorte.

    Cada `classification_dict` tiene la misma forma que produce
    `RealLongitudinalDataSource.list_classifications_with_templates_for_student`:
    `{episode_id, problema_id, template_id, unidad_id, classified_at,
    appropriation}`. Los estudiantes sin clasificaciones current simplemente no
    aparecen en el dict (el caller trata la ausencia como lista vacía → slope
    None), consistente con la función per-alumno.

    `language` (opcional, multi-language-research-integrity sección 4.8):
    restringe la cohorte a los episodios de ese lenguaje ANTES de resolver
    templates y traer clasificaciones — recalcula sobre el subconjunto en vez
    de filtrar después de agregar. Ausencia del parámetro preserva el
    comportamiento actual.
    """
    # Late imports (mismo patrón que real_datasources.py) para evitar ciclos.
    from academic_service.models.operacional import TareaPractica
    from classifier_service.models import Classification
    from ctr_service.models import Episode
    from platform_ops import DEFAULT_LANGUAGE, resolve_episode_languages

    # 1. Todos los episodios de la comisión → episode_id → (student, problema).
    ep_stmt = (
        select(Episode.id, Episode.student_pseudonym, Episode.problema_id)
        .where(Episode.comision_id == comision_id)
        .where(Episode.tenant_id == tenant_id)
    )
    ep_result = await ctr_session.execute(ep_stmt)
    ep_to_student: dict[UUID, UUID] = {}
    ep_to_problema: dict[UUID, UUID] = {}
    for row in ep_result.all():
        ep_to_student[row.id] = row.student_pseudonym
        ep_to_problema[row.id] = row.problema_id
    if not ep_to_student:
        return {}

    if language is not None:
        resolved = await resolve_episode_languages(
            ctr_session, tenant_id, list(ep_to_student.keys())
        )
        matching_ids = [
            eid for eid in ep_to_student if resolved.get(eid, DEFAULT_LANGUAGE) == language
        ]
        if not matching_ids:
            return {}
        ep_to_student = {eid: ep_to_student[eid] for eid in matching_ids}
        ep_to_problema = {eid: ep_to_problema[eid] for eid in matching_ids}

    # 2. Resolver problema_id → template_id + unidad_id (academic_main).
    problema_ids = list({pid for pid in ep_to_problema.values() if pid is not None})
    tp_data: dict[UUID, dict[str, Any]] = {}
    if problema_ids:
        tp_stmt = (
            select(TareaPractica.id, TareaPractica.template_id, TareaPractica.unidad_id)
            .where(TareaPractica.id.in_(problema_ids))
            .where(TareaPractica.tenant_id == tenant_id)
        )
        tp_result = await academic_session.execute(tp_stmt)
        tp_data = {
            row.id: {"template_id": row.template_id, "unidad_id": row.unidad_id}
            for row in tp_result.all()
        }

    # 3. Classifications current de esos episodios, ordenadas por fecha asc
    #    (mismo order_by que la función per-alumno — al agrupar se preserva el
    #    orden relativo dentro de cada estudiante).
    cls_stmt = (
        select(Classification)
        .where(Classification.comision_id == comision_id)
        .where(Classification.tenant_id == tenant_id)
        .where(Classification.is_current.is_(True))
        .where(Classification.episode_id.in_(ep_to_student.keys()))
        .order_by(Classification.classified_at.asc())
    )
    cls_result = await classifier_session.execute(cls_stmt)

    # 4. Agrupar por estudiante con template_id + unidad_id resueltos.
    grouped: dict[UUID, list[dict[str, Any]]] = {}
    for c in cls_result.scalars().all():
        student = ep_to_student.get(c.episode_id)
        if student is None:
            continue  # episodio de otra comisión (no debería con RLS)
        problema_id = ep_to_problema.get(c.episode_id)
        tp = tp_data.get(problema_id, {}) if problema_id else {}
        grouped.setdefault(student, []).append(
            {
                "episode_id": c.episode_id,
                "problema_id": problema_id,
                "template_id": tp.get("template_id"),
                "unidad_id": tp.get("unidad_id"),
                "classified_at": c.classified_at,
                "appropriation": c.appropriation,
            }
        )

    return grouped


__all__ = ["batch_classifications_with_templates_by_student"]
