"""Endpoints de Materias."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_db, require_permission
from academic_service.schemas import (
    ListMeta,
    ListResponse,
    MateriaCreate,
    MateriaInscripta,
    MateriaOut,
    MateriaUpdate,
)
from academic_service.services import MateriaService

router = APIRouter(prefix="/api/v1/materias", tags=["materias"])


@router.post("", response_model=MateriaOut, status_code=status.HTTP_201_CREATED)
async def create_materia(
    data: MateriaCreate,
    user: User = Depends(require_permission("materia", "create")),
    db: AsyncSession = Depends(get_db),
) -> MateriaOut:
    svc = MateriaService(db)
    obj = await svc.create(data, user)
    return MateriaOut.model_validate(obj)


@router.get("", response_model=ListResponse[MateriaOut])
async def list_materias(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    plan_id: str | None = None,
    user: User = Depends(require_permission("materia", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[MateriaOut]:
    # Aceptar query params vacios (plan_id=, cursor=) que el frontend manda
    # cuando el selector aun no eligio; Pydantic UUID rechaza string vacio con 422.
    plan_uuid: UUID | None = UUID(plan_id) if plan_id else None
    cursor_uuid: UUID | None = UUID(cursor) if cursor else None
    svc = MateriaService(db)
    objs = await svc.list(limit=limit, cursor=cursor_uuid, plan_id=plan_uuid)
    items = [MateriaOut.model_validate(o) for o in objs]
    next_cursor = str(objs[-1].id) if len(objs) == limit else None
    return ListResponse(data=items, meta=ListMeta(cursor_next=next_cursor))


@router.get("/mias", response_model=ListResponse[MateriaInscripta])
async def list_mis_materias(
    user: User = Depends(require_permission("materia", "read")),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[MateriaInscripta]:
    """Devuelve las materias en las que el estudiante autenticado está inscripto.

    Una fila por inscripción activa (Inscripcion.estado='activa', no soft-deleted),
    con datos planos de materia + comisión + período. La RLS de Postgres ya
    filtra por tenant_id (set_config en `tenant_session`); este endpoint suma
    el filtro adicional por `student_pseudonym = user.id`.

    Diseño deliberado: el alumno NO elige comisión, elige materia. La comisión
    es metadata derivada de su inscripción. Esto cierra el bug de
    `/comisiones/mis` que joinea contra `usuarios_comision` (docentes/JTP) y
    devuelve [] para estudiantes (gap B.2 documentado en CLAUDE.md).

    Sin paginación: el alumno típico tiene <10 materias en un cuatrimestre.
    """
    sql = text(
        """
        SELECT
            m.id            AS materia_id,
            m.codigo        AS materia_codigo,
            m.nombre        AS materia_nombre,
            c.id            AS comision_id,
            c.codigo        AS comision_codigo,
            c.nombre        AS comision_nombre,
            c.horario       AS comision_horario,
            p.id            AS periodo_id,
            p.codigo        AS periodo_codigo,
            i.id            AS inscripcion_id,
            i.fecha_inscripcion AS fecha_inscripcion
        FROM inscripciones i
        JOIN comisiones c ON c.id = i.comision_id
        JOIN materias m ON m.id = c.materia_id
        JOIN periodos p ON p.id = c.periodo_id
        WHERE i.student_pseudonym = :student_id
          AND i.estado IN ('activa', 'cursando')
          AND i.deleted_at IS NULL
          AND c.deleted_at IS NULL
          AND m.deleted_at IS NULL
          AND p.deleted_at IS NULL
        ORDER BY p.codigo DESC, m.codigo ASC
        """
    )
    result = await db.execute(sql, {"student_id": str(user.id)})
    rows = result.mappings().all()

    items: list[MateriaInscripta] = []
    for row in rows:
        # `comision_horario` es JSONB libre. Tomamos el primer string de los
        # values como hint humano; si no hay nada, queda en None.
        horario_resumen: str | None = None
        horario = row["comision_horario"] or {}
        if isinstance(horario, dict) and horario:
            for v in horario.values():
                if isinstance(v, str) and v.strip():
                    horario_resumen = v.strip()
                    break

        items.append(
            MateriaInscripta(
                materia_id=row["materia_id"],
                codigo=row["materia_codigo"],
                nombre=row["materia_nombre"],
                comision_id=row["comision_id"],
                comision_codigo=row["comision_codigo"],
                comision_nombre=row["comision_nombre"],
                horario_resumen=horario_resumen,
                periodo_id=row["periodo_id"],
                periodo_codigo=row["periodo_codigo"],
                inscripcion_id=row["inscripcion_id"],
                fecha_inscripcion=row["fecha_inscripcion"],
            )
        )
    return ListResponse(data=items, meta=ListMeta(total=len(items)))


@router.get("/{materia_id}", response_model=MateriaOut)
async def get_materia(
    materia_id: UUID,
    user: User = Depends(require_permission("materia", "read")),
    db: AsyncSession = Depends(get_db),
) -> MateriaOut:
    svc = MateriaService(db)
    obj = await svc.get(materia_id)
    return MateriaOut.model_validate(obj)


@router.patch("/{materia_id}", response_model=MateriaOut)
async def update_materia(
    materia_id: UUID,
    data: MateriaUpdate,
    user: User = Depends(require_permission("materia", "update")),
    db: AsyncSession = Depends(get_db),
) -> MateriaOut:
    svc = MateriaService(db)
    obj = await svc.update(materia_id, data, user)
    return MateriaOut.model_validate(obj)


@router.delete("/{materia_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_materia(
    materia_id: UUID,
    user: User = Depends(require_permission("materia", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = MateriaService(db)
    await svc.soft_delete(materia_id, user)
