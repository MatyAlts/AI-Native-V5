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
from platform_observability import verify_gateway_signature
from sqlalchemy.ext.asyncio import AsyncSession

from ctr_service.config import settings
from ctr_service.db import tenant_session


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

# Roles con visión total del CTR: oversight académico del tenant
# (superadmin / docente_admin) + service-accounts internos que leen
# service-to-service (tutor_service para idempotencia, classifier_worker para
# clasificar). Un `docente` "pelado" NO está acá: debe ser miembro de la
# comisión del episodio que quiere leer/verificar (gate A0.6).
CTR_OVERSIGHT_ROLES = frozenset(
    {"superadmin", "docente_admin", "tutor_service", "classifier_worker"}
)


async def _is_comision_member(tenant_id: UUID, user_id: UUID, comision_id: UUID) -> bool:
    """`True` si `user_id` es docente asignado a `comision_id` en academic_main.

    Query de solo-lectura contra `usuarios_comision` (academic_main) con RLS por
    tenant. El CTR no hace joins cross-base — usa una conexión separada. Seam
    aislado para poder testear el gate sin una DB académica real.
    """
    from platform_ops import set_tenant_rls
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from ctr_service.db import get_academic_engine

    engine = get_academic_engine()
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await set_tenant_rls(s, tenant_id)
        row = (
            await s.execute(
                text(
                    "SELECT 1 FROM usuarios_comision "
                    "WHERE comision_id = :c AND user_id = :u "
                    "AND deleted_at IS NULL LIMIT 1"
                ),
                {"c": str(comision_id), "u": str(user_id)},
            )
        ).first()
    return row is not None


async def assert_comision_member(user: User, comision_id: UUID) -> None:
    """Lanza 403 si `user` no puede leer el CTR de `comision_id` (gate A0.6).

    Cierra el leak: en prod todos los docentes comparten un tenant fijo, así que
    la RLS por tenant NO los separa — el aislamiento entre comisiones lo da la
    asignación `usuarios_comision`. Roles oversight y service-accounts internos
    (``CTR_OVERSIGHT_ROLES``) ven todo. Con el flag OFF o sin ``academic_db_url``
    (dev/stub/tests) el guard es no-op para no romper la auditoría legítima ni el
    dev loop. Mismo patrón que analytics-service.
    """
    if user.roles & CTR_OVERSIGHT_ROLES:
        return
    if not settings.enforce_comision_access or not settings.academic_db_url:
        return
    if not await _is_comision_member(user.tenant_id, user.id, comision_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenes acceso al CTR de esta comision (no sos docente asignado).",
        )
