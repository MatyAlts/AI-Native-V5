"""Auth dependencies para content-service.

Reutiliza el patrón del academic-service: headers X-* en F1/F2, JWT real
en F3 cuando el api-gateway valide firma.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from platform_observability import verify_gateway_signature
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.config import settings
from content_service.db import tenant_session
from content_service.models import Material


def _enforce_gateway_signature(
    x_user_id: str | None,
    x_tenant_id: str | None,
    x_user_roles: str | None,
    x_gateway_signature: str | None,
    x_gateway_ts: str | None,
) -> None:
    """Defensa en profundidad: exige firma HMAC del gateway si el flag está ON.

    Con ``require_gateway_signature=False`` (default) es un no-op total. Con el
    flag ON, valida procedencia de los headers de identidad sin re-verificar el
    JWT. Firma ausente/invalida => 401.
    """
    if not settings.require_gateway_signature:
        return
    ok = verify_gateway_signature(
        settings.gateway_shared_secret,
        x_user_id or "",
        x_tenant_id or "",
        x_user_roles or "",
        x_gateway_ts,  # type: ignore[arg-type]
        x_gateway_signature or "",
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma del gateway ausente o invalida",
        )


@dataclass(frozen=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[str]
    realm: str


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    x_gateway_signature: str | None = Header(default=None),
    x_gateway_ts: str | None = Header(default=None),
) -> User:
    # Defensa en profundidad (default OFF): exigir firma del gateway si el flag
    # está ON, antes de confiar en los headers X-*.
    _enforce_gateway_signature(
        x_user_id, x_tenant_id, x_user_roles, x_gateway_signature, x_gateway_ts
    )
    if x_user_id and x_tenant_id and x_user_email:
        return User(
            id=UUID(x_user_id),
            tenant_id=UUID(x_tenant_id),
            email=x_user_email,
            roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
            realm=x_tenant_id,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="JWT validation pending F3 api-gateway integration",
    )


async def get_db(user: User = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    async with tenant_session(user.tenant_id) as session:
        yield session


def require_role(*allowed_roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(allowed_roles)}",
            )
        return user

    return checker


# Roles que pueden subir material (F2)
MATERIAL_UPLOAD_ROLES = ("docente", "docente_admin", "superadmin")

# Roles que pueden llamar retrieval (F2 = docentes para testear; F3 = tutor-service
# con service-account + estudiantes con comisión_id validada)
RETRIEVAL_ROLES = ("docente", "docente_admin", "superadmin", "tutor_service")


# ── Propiedad/acceso por material (FIX C) ─────────────────────────────
#
# En prod el tenant = universidad, así que la RLS por tenant NO aísla docentes
# entre sí: sin este scope adicional cualquier docente del tenant podría leer el
# `contenido` de los chunks de OTRA materia, correr retrieval sobre cualquier
# `materia_id`, y —lo grave— `reingest` (destructivo) sobre CUALQUIER material.
#
# content-service NO tiene las tablas de pertenencia académica
# (`usuarios_comision` / `inscripciones` viven en academic_main, ADR-003; no se
# hacen joins cross-base). El scope mínimo defendible y fail-closed es la
# PROPIEDAD del material (`Material.uploaded_by`). Oversight académico del tenant
# (superadmin / docente_admin) ve todo — no rompe superadmin ni la coordinación.
#
# FOLLOW-UP (ABAC completo por comisión): resolver materia→comisión→membresía
# cruzando a academic-service (conexión `academic_db_url` dedicada + gate
# `enforce_comision_access`, mismo patrón que ctr-service/analytics-service)
# para habilitar co-docencia (docente B de la misma materia que no subió el
# material). Hoy queda fuera de scope: el owner-scoping ya cierra el leak y el
# reingest destructivo.
CONTENT_OVERSIGHT_ROLES = frozenset({"superadmin", "docente_admin"})


def assert_material_owner(user: User, material: Material) -> None:
    """Fail-closed: el caller sólo accede a un material que subió él.

    Scope de propiedad por `Material.uploaded_by` (la RLS por tenant no aísla
    docentes en prod). Oversight (superadmin / docente_admin) ve todo. Devuelve
    404 (no 403) para no filtrar la existencia de materiales ajenos del tenant.
    """
    if user.roles & CONTENT_OVERSIGHT_ROLES:
        return
    if material.uploaded_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material {material.id} no encontrado",
        )


async def assert_materia_upload_access(
    session: AsyncSession, user: User, materia_id: UUID
) -> None:
    """Fail-closed: el caller sólo corre retrieval sobre materias donde subió material.

    Sin `usuarios_comision`/`inscripciones` locales (ADR-003), el scope mínimo
    defendible es la propiedad de material dentro de la materia: si el caller no
    subió ningún material vivo a `materia_id`, no puede correr retrieval sobre
    ella (403). Oversight (superadmin / docente_admin) no se restringe.
    """
    if user.roles & CONTENT_OVERSIGHT_ROLES:
        return
    row = (
        await session.execute(
            select(Material.id)
            .where(
                Material.materia_id == materia_id,
                Material.uploaded_by == user.id,
                Material.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No tenes material propio en esta materia; "
                "no podes correr retrieval sobre ella."
            ),
        )
