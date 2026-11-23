"""Endpoints para auto-llenado del perfil del alumno (full_name + email).

POST /api/v1/users/me/profile
    Upsert idempotente: el web-student lo invoca al loguearse con Clerk.
    Body: {full_name, email}. Caller_id = student_pseudonym del header. El
    email que se guarda y con el que se vinculan las asignaciones docentes es
    el del token, no el del body (HU-017).

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
from academic_service.services.comision_service import assert_comision_member

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

    HU-017: el email que cuenta es el del TOKEN (`user.email`: el gateway lo
    saca del claim `email` del JWT de Clerk y pisa `X-User-Email`), nunca el
    del body. Antes se vinculaba `usuarios_comision` con `data.email` sin
    verificar, y un alumno que mandaba el email de un docente pasaba a ser
    miembro de sus comisiones. El `email` del body se acepta por compatibilidad
    con el frontend pero se ignora; sin email en el token no se guarda email ni
    se vincula nada.
    """
    email_token = (user.email or "").strip()
    email_perfil = email_token or None
    stmt = (
        pg_insert(StudentProfile)
        .values(
            student_pseudonym=user.id,
            tenant_id=user.tenant_id,
            full_name=data.full_name,
            email=email_perfil,
        )
        .on_conflict_do_update(
            index_elements=["student_pseudonym"],
            set_={
                "full_name": data.full_name,
                "email": email_perfil,
                "tenant_id": user.tenant_id,
            },
        )
        .returning(StudentProfile)
    )
    result = await db.execute(stmt)
    profile = result.scalar_one()

    # Resolución de asignaciones docentes por email: el admin asigna al docente
    # por email (antes de que se loguee). Al loguearse, vinculamos esas
    # asignaciones a su user_id REAL (derivado del token). Idempotente y
    # re-vinculante: el registro con ese email siempre queda con la identidad
    # del login actual (cubre el caso de un user_id viejo/demo previo). El
    # email es el del token (HU-017), comparado sin mayúsculas.
    if email_token:
        await db.execute(
            update(UsuarioComision)
            .where(
                func.lower(UsuarioComision.email) == email_token.lower(),
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
    # Cierra el leak: un docente solo puede ver los perfiles de SUS comisiones
    # (staff). Sin esto, cualquier docente veria los pseudonimos de alumnos de
    # cualquier comision (require_role solo valida el rol generico, no la
    # pertenencia a esta comision puntual).
    await assert_comision_member(db, user, comision_id)
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
