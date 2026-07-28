"""Auth del execution-service (mismo patron que el resto de los servicios).

El api-gateway es el UNICO source of truth de identidad: los servicios internos
confian en los headers `X-Tenant-Id` / `X-User-Id` / `X-User-Roles` que el
gateway inyecta autoritativamente, y NO re-verifican el JWT aguas abajo.

`require_gateway_signature` (default OFF) agrega defensa en profundidad: con el
flag ON se exige la firma HMAC del gateway sobre esos headers antes de confiar
en ellos. Se prende recien despues de configurar el secreto compartido en todos
los callers, o se corta el trafico legitimo.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from platform_observability import verify_gateway_signature

from execution_service.config import settings


@dataclass(frozen=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[str]


def _enforce_gateway_signature(
    x_user_id: str | None,
    x_tenant_id: str | None,
    x_user_roles: str | None,
    x_gateway_signature: str | None,
    x_gateway_ts: str | None,
) -> None:
    """No-op con el flag OFF (default). Con el flag ON, firma ausente => 401."""
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


async def get_current_user(
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    x_gateway_signature: str | None = Header(default=None),
    x_gateway_ts: str | None = Header(default=None),
) -> User:
    _enforce_gateway_signature(
        x_user_id, x_tenant_id, x_user_roles, x_gateway_signature, x_gateway_ts
    )
    if not (x_user_id and x_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faltan headers de identidad del gateway",
        )
    try:
        user_id = UUID(x_user_id)
        tenant_id = UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Headers de identidad malformados",
        ) from exc

    return User(
        id=user_id,
        tenant_id=tenant_id,
        email=x_user_email or "",
        roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
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
