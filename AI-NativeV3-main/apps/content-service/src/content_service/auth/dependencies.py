"""Auth dependencies para content-service.

Reutiliza el patrón del academic-service: headers X-* en F1/F2, JWT real
en F3 cuando el api-gateway valide firma.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.db import tenant_session


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
                detail=f"Se requiere uno de los roles: {', '.join(allowed_roles)}",
            )
        return user

    return checker


# Roles que pueden subir material (F2)
MATERIAL_UPLOAD_ROLES = ("docente", "docente_admin", "superadmin")

# Roles que pueden llamar retrieval (F2 = docentes para testear; F3 = tutor-service
# con service-account + estudiantes con comisión_id validada)
RETRIEVAL_ROLES = ("docente", "docente_admin", "superadmin", "tutor_service")
