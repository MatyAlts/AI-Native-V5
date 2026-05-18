"""Auth del ctr-service.

El CTR es escrito principalmente por service-accounts (tutor-service),
no por usuarios finales directamente. Los docentes pueden LEER episodios
completos de sus comisiones. Superadmin puede leer cualquiera.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ctr_service.db import tenant_session


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
) -> User:
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
                detail=f"Se requiere uno de: {', '.join(allowed_roles)}",
            )
        return user

    return checker


# Publicar eventos: solo service-accounts (en F3 usar cliente autenticado
# con credenciales de servicio)
PUBLISH_ROLES = ("tutor_service", "superadmin")

# Leer episodios: docentes (solo los de sus comisiones; ABAC adicional),
# docente_admin del tenant, superadmin
READ_ROLES = ("docente", "docente_admin", "superadmin", "tutor_service", "classifier_worker")
