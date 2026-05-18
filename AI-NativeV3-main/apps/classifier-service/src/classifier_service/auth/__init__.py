"""Auth del classifier-service."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status


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
    if x_user_id and x_tenant_id and x_user_email:
        return User(
            id=UUID(x_user_id),
            tenant_id=UUID(x_tenant_id),
            email=x_user_email,
            roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
            realm=x_tenant_id,
        )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")


def require_role(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.roles.intersection(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Requiere: {', '.join(roles)}"
            )
        return user

    return checker


CLASSIFY_ROLES = ("docente", "docente_admin", "superadmin", "classifier_worker")
READ_ROLES = ("docente", "docente_admin", "superadmin", "estudiante")


__all__ = ["CLASSIFY_ROLES", "READ_ROLES", "User", "get_current_user", "require_role"]
