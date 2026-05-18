"""Dependencies de FastAPI para auth del evaluation-service.

Mismo patron que academic-service: los headers X-* son inyectados por
el api-gateway (que valida el JWT). Los servicios internos confian en
esos headers sin re-validar.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.db import tenant_session


@dataclass(frozen=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[str]
    realm: str


async def get_current_user(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
) -> User:
    if not (x_user_id and x_tenant_id and x_user_email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth headers (X-User-Id, X-Tenant-Id, X-User-Email)",
        )
    return User(
        id=UUID(x_user_id),
        tenant_id=UUID(x_tenant_id),
        email=x_user_email,
        roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
        realm=x_tenant_id,
    )


async def get_db(user: User = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    async with tenant_session(user.tenant_id) as session:
        yield session


def require_permission(resource: str, action: str):
    """Simplificado: en v1 usamos roles directos sin Casbin enforcer completo.

    El Casbin completo del academic-service es la fuente de verdad para
    politicas — evaluation-service verifica roles directamente por ahora.
    Roles con permisos amplios: superadmin, docente_admin, docente.
    """
    DOCENTE_ROLES = frozenset({"superadmin", "docente_admin", "docente", "jtp", "auxiliar"})
    STUDENT_READABLE = {"entrega", "calificacion"}

    async def checker(user: User = Depends(get_current_user)) -> User:
        # superadmin bypasa todo
        if "superadmin" in user.roles:
            return user

        # docentes pueden leer/crear/actualizar dentro de su scope
        if user.roles & DOCENTE_ROLES:
            return user

        # estudiantes pueden leer sus propios datos
        if "estudiante" in user.roles:
            if resource in STUDENT_READABLE and action == "read":
                return user
            if resource == "entrega" and action == "create":
                return user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado: {action} sobre {resource}",
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permiso denegado: {action} sobre {resource}",
        )

    return checker
