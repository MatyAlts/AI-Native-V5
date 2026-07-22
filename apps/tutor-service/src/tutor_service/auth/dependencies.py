"""Auth del tutor-service (mismo patrón que otros servicios)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from platform_observability import verify_gateway_signature

from tutor_service.config import settings


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
        detail="JWT validation pending F5 api-gateway integration",
    )


def require_role(*allowed_roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requiere uno de: {', '.join(allowed_roles)}",
            )
        return user

    return checker
