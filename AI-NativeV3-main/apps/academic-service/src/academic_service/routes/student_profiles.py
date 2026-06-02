"""Endpoints para auto-llenado del perfil del alumno (full_name + email).

POST /api/v1/users/me/profile
    Upsert idempotente: el web-student lo invoca al loguearse con Clerk.
    Body: {full_name, email}. Caller_id = student_pseudonym del header.

GET /api/v1/comisiones/{comision_id}/students/profiles
    Listado de perfiles de los alumnos inscriptos en la comision. Solo
    accesible al docente/docente_admin/superadmin. RLS de tenant + filtro
    por inscripcion en la comision. Alumnos sin profile devuelven full_name=None.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.auth import User, get_current_user, get_db, require_role
from academic_service.models.operacional import Inscripcion, UsuarioComision
from academic_service.models.transversal import StudentProfile
from academic_service.schemas.student_profile import StudentProfileOut, StudentProfileUpsert

users_router = APIRouter(prefix="/api/v1/users", tags=["users"])


@users_router.post("/me/profile", status_code=status.HTTP_200_OK, response_model=StudentProfileOut)
async def upsert_my_profile(
    data: StudentProfileUpsert,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudentProfile:
    """Upsert idempotente del perfil del usuario logueado.

    El web-student lo invoca al iniciar sesion con Clerk con el nombre
    y email del usuario. Si ya existia, actualiza los campos.
    """
    stmt = (
        pg_insert(StudentProfile)
        .values(
            student_pseudonym=user.id,
            tenant_id=user.tenant_id,
            full_name=data.full_name,
            email=str(data.email) if data.email else None,
        )
        .on_conflict_do_update(
            index_elements=["student_pseudonym"],
            set_={
                "full_name": data.full_name,
                "email": str(data.email) if data.email else None,
                "tenant_id": user.tenant_id,
            },
        )
        .returning(StudentProfile)
    )
    result = await db.execute(stmt)
    profile = result.scalar_one()

    # Resolución de asignaciones docentes pendientes: el admin pudo haber
    # asignado a este usuario como docente por email ANTES de su primer login.
    # Ahora que conocemos su user_id real (derivado de Clerk), lo vinculamos a
    # esas comisiones para que aparezcan en GET /comisiones/mis.
    if data.email:
        await db.execute(
            update(UsuarioComision)
            .where(
                func.lower(UsuarioComision.email) == data.email.strip().lower(),
                UsuarioComision.user_id.is_(None),
                UsuarioComision.tenant_id == user.tenant_id,
            )
            .values(user_id=user.id)
        )

    await db.commit()
    return profile


# Endpoint del docente: monta sobre el prefix /api/v1/comisiones existente
# para que el ROUTE_MAP del api-gateway lo cubra sin agregar entradas nuevas.
comisiones_profiles_router = APIRouter(prefix="/api/v1/comisiones", tags=["users"])


@comisiones_profiles_router.get(
    "/{comision_id}/students/profiles",
    response_model=list[StudentProfileOut],
)
async def list_student_profiles_for_comision(
    comision_id: UUID,
    user: User = Depends(require_role("docente", "docente_admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> list[StudentProfileOut]:
    """Lista los perfiles de alumnos inscriptos en la comision.

    Devuelve UNA fila por inscripcion activa. Si el alumno todavia no
    hizo POST /me/profile, full_name y email vienen None y el frontend
    cae al `Est. xxxxxx` como fallback.
    """
    _ = user
    stmt = (
        select(
            Inscripcion.student_pseudonym,
            StudentProfile.full_name,
            StudentProfile.email,
            StudentProfile.updated_at,
        )
        .select_from(Inscripcion)
        .outerjoin(
            StudentProfile,
            StudentProfile.student_pseudonym == Inscripcion.student_pseudonym,
        )
        .where(
            Inscripcion.comision_id == comision_id,
            Inscripcion.deleted_at.is_(None),
        )
    )
    rows = (await db.execute(stmt)).all()
    out: list[StudentProfileOut] = []
    for r in rows:
        out.append(
            StudentProfileOut(
                student_pseudonym=r.student_pseudonym,
                full_name=r.full_name,
                email=r.email,
                updated_at=r.updated_at,
            )
        )
    return out
