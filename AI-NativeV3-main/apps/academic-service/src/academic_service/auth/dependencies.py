"""Dependencies de FastAPI para auth y tenant context.

En F1 el JWT se valida contra Keycloak. Para tests, se inyecta un User
mock. La validación real con firma de JWT se completa en F3 cuando el
api-gateway toma ese rol.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.db import tenant_session


@dataclass(frozen=True)
class User:
    """Usuario autenticado extraído del JWT."""

    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[str]
    realm: str
    comisiones_activas: frozenset[UUID] = frozenset()


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),  # solo para tests locales
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
) -> User:
    """Extrae el usuario del header Authorization (JWT Keycloak).

    En F1/F2 (antes de que api-gateway tome el rol de validar JWTs)
    aceptamos headers X-* para facilitar pruebas end-to-end locales.
    En F3, el api-gateway valida el JWT y agrega estos headers; los
    servicios downstream solo los leen, confiando en la validación
    del gateway.
    """
    # Path de desarrollo/test: headers X-* inyectados por el api-gateway
    # o por el cliente de tests
    if x_user_id and x_tenant_id and x_user_email:
        return User(
            id=UUID(x_user_id),
            tenant_id=UUID(x_tenant_id),
            email=x_user_email,
            roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
            realm=x_tenant_id,  # por simplicidad
        )

    # DEFERRED F3: validar firma JWT contra Keycloak y extraer claims acá.
    # Bloqueante hasta que el api-gateway tome rol de validador (ADR auth/F3).
    # Mientras tanto el path X-* arriba cubre dev/test y prod via gateway.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Placeholder: en F3 esto valida firma del JWT
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="JWT validation pending F3 api-gateway integration",
    )


async def get_db(user: User = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    """Sesión DB con tenant del user activo seteado en RLS."""
    async with tenant_session(user.tenant_id) as session:
        yield session


def require_role(*allowed_roles: str):
    """Dependency factory que exige al menos uno de los roles."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(allowed_roles)}",
            )
        return user

    return checker
