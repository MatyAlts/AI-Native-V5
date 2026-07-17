"""Endpoints CRUD de BYOK keys (ADR-039, Sec 7 epic ai-native-completion).

Solo `superadmin` y `docente_admin` pueden gestionar keys (Casbin policy
`byok_key:CRUD` registrada en `apps/academic-service/.../seeds/casbin_policies.py`
— por ahora la verificacion vive aca via X-User-Roles, mejorable con un
PEP de Casbin compartido).

Endpoints:
  POST   /api/v1/byok/keys
  GET    /api/v1/byok/keys
  POST   /api/v1/byok/keys/{id}/rotate
  POST   /api/v1/byok/keys/{id}/revoke
  GET    /api/v1/byok/keys/{id}/usage
  POST   /api/v1/byok/keys/{id}/test  -> 501 Not Implemented (NB-23, ver abajo)

Diferidos a follow-up (NO implementados). El endpoint `/test` existe pero
responde 501 explicito — la validacion real de una key contra su provider
NO esta implementada y no debe documentarse como capacidad disponible hasta
que los adapters existan:
  Validacion de una key contra su provider (requiere adapters de proveedor)
  Cache Redis del resolver
  Adapters Gemini/Mistral
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ai_gateway.auth import require_gateway_auth
from ai_gateway.services.byok import (
    BYOKConflictError,
    create_byok_key,
    get_byok_key_usage,
    list_byok_keys,
    revoke_byok_key,
    rotate_byok_key,
)

# Auth de procedencia a nivel router (A0.1): con `require_gateway_signature` ON
# todos los endpoints BYOK exigen firma del gateway o token de service-account.
# Con el flag OFF (default) es no-op y NO altera los checks de rol (_check_admin/
# _check_read de F11) que siguen corriendo por debajo via las deps _get_actor*.
router = APIRouter(
    prefix="/api/v1/byok",
    tags=["byok"],
    dependencies=[Depends(require_gateway_auth)],
)

_ADMIN_ROLES = {"superadmin", "docente_admin"}
# Lectura read-only (GET keys / usage): admite ademas al docente (F11 — uso/costo
# de IA para el docente). Las mutaciones siguen exigiendo _ADMIN_ROLES.
_READ_ROLES = _ADMIN_ROLES | {"docente"}


def _check_admin(roles_header: str) -> set[str]:
    roles = {r.strip() for r in (roles_header or "").split(",") if r.strip()}
    if not (_ADMIN_ROLES & roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="byok_key:CRUD requiere rol superadmin o docente_admin",
        )
    return roles


def _check_read(roles_header: str) -> set[str]:
    roles = {r.strip() for r in (roles_header or "").split(",") if r.strip()}
    if not (_READ_ROLES & roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="byok_key:read requiere rol docente, docente_admin o superadmin",
        )
    return roles


def _parse_actor(x_tenant_id: str, x_user_id: str) -> tuple[UUID, UUID]:
    try:
        return UUID(x_tenant_id), UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Headers UUID invalidos"
        ) from exc


async def _get_actor(
    x_tenant_id: str = Header(),
    x_user_id: str = Header(),
    x_user_roles: str = Header(""),
) -> tuple[UUID, UUID]:
    """Auth de mutacion — el api-gateway inyecta los headers autoritativos."""
    _check_admin(x_user_roles)
    return _parse_actor(x_tenant_id, x_user_id)


async def _get_actor_read(
    x_tenant_id: str = Header(),
    x_user_id: str = Header(),
    x_user_roles: str = Header(""),
) -> tuple[UUID, UUID]:
    """Auth de lectura (GET keys/usage) — admite docente read-only (F11)."""
    _check_read(x_user_roles)
    return _parse_actor(x_tenant_id, x_user_id)


# ── Schemas ────────────────────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    scope_type: Literal["tenant", "facultad", "materia"]
    scope_id: UUID | None = None
    provider: Literal["anthropic", "gemini", "mistral", "openai", "openrouter"]
    plaintext_value: str = Field(min_length=8, max_length=512)
    monthly_budget_usd: float | None = Field(default=None, ge=0.0)

    @field_validator("scope_id", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: object) -> UUID | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return UUID(v)
            except ValueError:
                raise ValueError(f"scope_id debe ser un UUID valido, recibido: {v!r}")
        if isinstance(v, UUID):
            return v
        raise ValueError(f"scope_id debe ser UUID o string, recibido: {type(v).__name__}")


class RotateKeyRequest(BaseModel):
    plaintext_value: str = Field(min_length=8, max_length=512)


class KeyOut(BaseModel):
    id: str
    tenant_id: str
    scope_type: str
    scope_id: str | None
    provider: str
    fingerprint_last4: str
    monthly_budget_usd: float | None
    created_at: str
    created_by: str
    revoked_at: str | None
    last_used_at: str | None


class UsageOut(BaseModel):
    key_id: str
    yyyymm: str
    tokens_input_total: int
    tokens_output_total: int
    cost_usd_total: float
    request_count: int


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post("/keys", response_model=KeyOut, status_code=status.HTTP_201_CREATED)
async def post_create_key(
    req: CreateKeyRequest,
    actor: tuple[UUID, UUID] = Depends(_get_actor),
) -> KeyOut:
    """Crea una BYOK key encriptada.

    NO valida contra el provider en piloto-1 (eso requiere los adapters
    Gemini/Mistral que estan diferidos). Si la key es invalida, el primer
    request al ai-gateway que la resuelva fallara y el admin puede revocar.

    Errores comunes:
      - 400 si scope_type/scope_id inconsistentes
      - 403 si caller no es admin
      - 409 si ya existe una key activa para (scope, scope_id, provider)
      - 500 si BYOK_MASTER_KEY no esta seteada
    """
    tenant_id, user_id = actor
    try:
        key = await create_byok_key(
            tenant_id=tenant_id,
            user_id=user_id,
            scope_type=req.scope_type,
            scope_id=req.scope_id,
            provider=req.provider,
            plaintext_value=req.plaintext_value,
            monthly_budget_usd=req.monthly_budget_usd,
        )
    except BYOKConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if "BYOK_MASTER_KEY" in msg:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    return KeyOut(**key)


@router.get("/keys", response_model=list[KeyOut])
async def get_list_keys(
    scope_type: Literal["tenant", "facultad", "materia"] | None = None,
    scope_id: UUID | None = None,
    actor: tuple[UUID, UUID] = Depends(_get_actor_read),
) -> list[KeyOut]:
    """Lista keys del tenant. NO devuelve el plaintext — solo metadata
    + `fingerprint_last4`."""
    tenant_id, _ = actor
    rows = await list_byok_keys(tenant_id, scope_type=scope_type, scope_id=scope_id)
    return [KeyOut(**r) for r in rows]


@router.post("/keys/{key_id}/rotate", response_model=KeyOut)
async def post_rotate_key(
    key_id: UUID,
    req: RotateKeyRequest,
    actor: tuple[UUID, UUID] = Depends(_get_actor),
) -> KeyOut:
    """Rota el plaintext de una BYOK key existente.

    Sec 7.3 epic ai-native-completion-and-byok. Reemplaza `encrypted_value` y
    `fingerprint_last4` con el nuevo plaintext encriptado. Preserva `id`,
    `scope`, `created_at`, `created_by` — la rotacion es invisible al resolver
    y a los callers que ya tienen el `key_id` cacheado.

    Errores:
      - 404 si la key no existe o esta revocada (crear una nueva).
      - 400 si el plaintext es invalido (formato, length).
      - 500 si BYOK_MASTER_KEY no esta configurada.
    """
    tenant_id, _ = actor
    try:
        key = await rotate_byok_key(tenant_id, key_id, req.plaintext_value)
    except ValueError as exc:
        msg = str(exc)
        if "BYOK_MASTER_KEY" in msg:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key {key_id} no encontrada o revocada (crear una nueva)",
        )
    return KeyOut(**key)


@router.post("/keys/{key_id}/revoke", response_model=KeyOut)
async def post_revoke_key(
    key_id: UUID,
    actor: tuple[UUID, UUID] = Depends(_get_actor),
) -> KeyOut:
    """Soft-revoke: setea `revoked_at`. La key queda en disco para audit
    pero el resolver la ignora (filter `revoked_at IS NULL`)."""
    tenant_id, _ = actor
    key = await revoke_byok_key(tenant_id, key_id)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Key {key_id} no encontrada"
        )
    return KeyOut(**key)


@router.get("/keys/{key_id}/usage", response_model=UsageOut)
async def get_key_usage(
    key_id: UUID,
    yyyymm: str | None = None,
    actor: tuple[UUID, UUID] = Depends(_get_actor_read),
) -> UsageOut:
    """Devuelve el agregado de uso del mes (por default el actual).

    Stub-friendly: si la key nunca se uso, devuelve 0s — no falla.
    """
    tenant_id, _ = actor
    usage = await get_byok_key_usage(tenant_id, key_id, yyyymm=yyyymm)
    return UsageOut(**usage)


@router.post(
    "/keys/{key_id}/test",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={
        501: {
            "description": "No implementado — requiere adapters de proveedor "
            "(diferidos a follow-up)."
        }
    },
)
async def post_test_key(
    key_id: UUID,
    actor: tuple[UUID, UUID] = Depends(_get_actor),
) -> None:
    """Validar una BYOK key contra su proveedor — DIFERIDO / NO IMPLEMENTADO (NB-23).

    Esta capacidad estuvo *documentada* como follow-up pero nunca se implemento:
    validar una key contra el provider requiere los adapters de proveedor
    (Gemini/Mistral/etc.) que estan diferidos. En vez de fingir la validacion o
    de dejar un 404 ambiguo (que se lee como un bug de ruteo), el endpoint existe
    y responde **501 Not Implemented** con un mensaje claro — la ausencia de la
    feature queda explicita en la superficie de la API, no escondida en un docstring.

    Hasta que existan los adapters, la unica validacion real de una key ocurre
    cuando el primer request LLM que la resuelve la usa (y falla si es invalida);
    el admin puede entonces revocar/rotar. Ver `post_create_key` (no valida al crear).

    Cuando se implementen los adapters, reemplazar este stub por la validacion real
    y actualizar el docstring del modulo (mover `/test` fuera de "Diferidos").
    """
    _ = key_id, actor  # gate de auth via _get_actor; el body es intencionalmente no-op
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Probar una BYOK key contra el proveedor no esta implementado: "
            "requiere los adapters de proveedor, diferidos a follow-up. Para "
            "validar una key, usala en un request LLM real y revisa si falla."
        ),
    )
