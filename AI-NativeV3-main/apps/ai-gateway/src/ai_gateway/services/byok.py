"""BYOK (Bring-Your-Own-Key) — modelo SQLA, resolver, CRUD.

Sec 5+7 epic ai-native-completion-and-byok / ADR-038 + ADR-039.

Modelo:
    BYOKKey: una API key configurada por (tenant, scope_type, scope_id, provider).
        scope_type IN ('tenant', 'facultad', 'materia').
        scope_type='tenant' => scope_id IS NULL.
        scope_type='facultad'/'materia' => scope_id NOT NULL.

Resolver jerarquico:
    1. Lookup byok_keys con scope=materia, scope_id=materia_id (si dado).
    2. Lookup byok_keys con scope=facultad (resolviendo facultad_id desde
       materia_id — TODO: cache Redis materia:{id}:facultad_id, deferido).
    3. Lookup byok_keys con scope=tenant.
    4. Env var legacy del provider (ANTHROPIC_API_KEY, etc.) — fallback.
    5. None => caller decide 503.

Encriptacion: ADR-038 / `packages/platform-ops/src/platform_ops/crypto.py`.
La master key viene de `BYOK_MASTER_KEY` env var (32 bytes base64).
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    LargeBinary,
    Numeric,
    String,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ai_gateway.config import settings
from ai_gateway.metrics import (
    byok_key_resolution_duration_seconds,
    byok_key_resolution_total,
    byok_key_usage_total,
)

logger = logging.getLogger(__name__)


class _BYOKBase(DeclarativeBase):
    """Base SQLA local del ai-gateway. Las tablas viven en academic_main."""


class BYOKKey(_BYOKBase):
    __tablename__ = "byok_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fingerprint_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    created_by: Mapped[UUID] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BYOKKeyUsage(_BYOKBase):
    __tablename__ = "byok_keys_usage"

    key_id: Mapped[UUID] = mapped_column(
        ForeignKey("byok_keys.id", ondelete="CASCADE"), primary_key=True
    )
    yyyymm: Mapped[str] = mapped_column(String(6), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    tokens_input_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tokens_output_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd_total: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


# ── Engine + Session helpers ──────────────────────────────────────────


_engine = None
_sessionmaker = None


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_async_engine(settings.academic_db_url, pool_size=5)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def _set_tenant_rls(session: AsyncSession, tenant_id: UUID) -> None:
    """SET LOCAL app.current_tenant para activar las RLS policies.

    Mismo patron que `packages/platform-ops/.../real_datasources.py::set_tenant_rls`.

    Nota: Postgres NO permite bind parameters en `SET LOCAL` (es un utility
    statement). Usamos `set_config(name, value, is_local=true)` que es
    semanticamente equivalente a `SET LOCAL` y SI acepta bind params —
    evita inyeccion SQL sin recurrir a interpolacion literal.
    """
    from sqlalchemy import text

    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )


# ── Master key + crypto helpers ────────────────────────────────────────


def _get_master_key_bytes() -> bytes | None:
    """Lee `BYOK_MASTER_KEY` env var (base64 de 32 bytes).

    Devuelve None si no esta configurada — el caller decide si fallback a
    env legacy o 503.
    """
    if not settings.byok_master_key:
        return None
    try:
        decoded = base64.b64decode(settings.byok_master_key, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        logger.error("byok_master_key_invalid_base64: %s", exc)
        return None
    if len(decoded) != 32:
        logger.error("byok_master_key_wrong_size: got %d bytes (expected 32)", len(decoded))
        return None
    return decoded


# ── Resolver ───────────────────────────────────────────────────────────


@dataclass
class ResolvedKey:
    plaintext: str
    provider: str
    scope_resolved: str  # "materia" | "facultad" | "tenant" | "env_fallback"
    key_id: UUID | None  # None si vino de env fallback
    monthly_budget_usd: float | None


def _env_fallback_key(provider: str) -> str | None:
    """Devuelve la key del env legacy o None."""
    mapping = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "mistral": settings.mistral_api_key,
    }
    val = mapping.get(provider, "")
    return val if val else None


async def resolve_byok_key(
    tenant_id: UUID,
    provider: str,
    materia_id: UUID | None = None,
) -> ResolvedKey | None:
    """Resolver jerarquico (ADR-039):
    1. scope=materia + scope_id=materia_id (si dado).
    2. scope=tenant + scope_id=NULL.
       (scope=facultad omitido en piloto-1 — requiere lookup cross-DB
       materia.facultad_id que va con cache Redis en piloto-2.)
    3. Env fallback (ANTHROPIC_API_KEY, etc.).

    Si BYOK_ENABLED=False, salta directo al env fallback.

    Sec 13.1-13.2 epic: emite contadores `byok_key_resolution_total{resolved_scope=...}`,
    `byok_key_usage_total{provider, scope_type, resolved_scope}` (cuando hay match
    DB, no env_fallback) y un histogram `byok_key_resolution_duration_seconds`
    con el wall-clock time del resolver. SLO p99 < 50ms.
    """
    _t0 = time.perf_counter()

    def _emit(result: ResolvedKey | None, scope_label: str) -> ResolvedKey | None:
        elapsed = time.perf_counter() - _t0
        byok_key_resolution_duration_seconds.record(elapsed, {"resolved_scope": scope_label})
        byok_key_resolution_total.add(1, {"resolved_scope": scope_label})
        # Solo cuenta usage cuando hay key real (no env_fallback ni none).
        if result is not None and result.scope_resolved in ("materia", "tenant", "facultad"):
            byok_key_usage_total.add(
                1,
                {
                    "provider": provider,
                    "scope_type": result.scope_resolved,
                    "resolved_scope": result.scope_resolved,
                },
            )
        return result

    if not settings.byok_enabled:
        env = _env_fallback_key(provider)
        if env is None:
            return _emit(None, "none")
        return _emit(
            ResolvedKey(
                plaintext=env,
                provider=provider,
                scope_resolved="env_fallback",
                key_id=None,
                monthly_budget_usd=None,
            ),
            "env_fallback",
        )

    master_key = _get_master_key_bytes()
    if master_key is None:
        # Sin master key no podemos desencriptar — fallback directo a env
        env = _env_fallback_key(provider)
        if env is None:
            return _emit(None, "none")
        return _emit(
            ResolvedKey(
                plaintext=env,
                provider=provider,
                scope_resolved="env_fallback",
                key_id=None,
                monthly_budget_usd=None,
            ),
            "env_fallback",
        )

    from platform_ops.crypto import CryptoError, decrypt

    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)

        # 1. scope=materia
        if materia_id is not None:
            stmt = (
                select(BYOKKey)
                .where(BYOKKey.tenant_id == tenant_id)
                .where(BYOKKey.scope_type == "materia")
                .where(BYOKKey.scope_id == materia_id)
                .where(BYOKKey.provider == provider)
                .where(BYOKKey.revoked_at.is_(None))
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                try:
                    plaintext = decrypt(row.encrypted_value, master_key).decode("utf-8")
                except CryptoError as exc:
                    logger.error("byok_decrypt_failed key_id=%s: %s", row.id, exc)
                else:
                    return _emit(
                        ResolvedKey(
                            plaintext=plaintext,
                            provider=provider,
                            scope_resolved="materia",
                            key_id=row.id,
                            monthly_budget_usd=(
                                float(row.monthly_budget_usd)
                                if row.monthly_budget_usd is not None
                                else None
                            ),
                        ),
                        "materia",
                    )

        # 2. scope=facultad (any key with scope_type='facultad' for this tenant+provider)
        stmt = (
            select(BYOKKey)
            .where(BYOKKey.tenant_id == tenant_id)
            .where(BYOKKey.scope_type == "facultad")
            .where(BYOKKey.provider == provider)
            .where(BYOKKey.revoked_at.is_(None))
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            try:
                plaintext = decrypt(row.encrypted_value, master_key).decode("utf-8")
            except CryptoError as exc:
                logger.error("byok_decrypt_failed key_id=%s: %s", row.id, exc)
            else:
                return _emit(
                    ResolvedKey(
                        plaintext=plaintext,
                        provider=provider,
                        scope_resolved="facultad",
                        key_id=row.id,
                        monthly_budget_usd=(
                            float(row.monthly_budget_usd)
                            if row.monthly_budget_usd is not None
                            else None
                        ),
                    ),
                    "facultad",
                )

        # 3. scope=tenant
        stmt = (
            select(BYOKKey)
            .where(BYOKKey.tenant_id == tenant_id)
            .where(BYOKKey.scope_type == "tenant")
            .where(BYOKKey.scope_id.is_(None))
            .where(BYOKKey.provider == provider)
            .where(BYOKKey.revoked_at.is_(None))
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            try:
                plaintext = decrypt(row.encrypted_value, master_key).decode("utf-8")
            except CryptoError as exc:
                logger.error("byok_decrypt_failed key_id=%s: %s", row.id, exc)
            else:
                return _emit(
                    ResolvedKey(
                        plaintext=plaintext,
                        provider=provider,
                        scope_resolved="tenant",
                        key_id=row.id,
                        monthly_budget_usd=(
                            float(row.monthly_budget_usd)
                            if row.monthly_budget_usd is not None
                            else None
                        ),
                    ),
                    "tenant",
                )

    # 4. Env fallback
    env = _env_fallback_key(provider)
    if env is None:
        return _emit(None, "none")
    return _emit(
        ResolvedKey(
            plaintext=env,
            provider=provider,
            scope_resolved="env_fallback",
            key_id=None,
            monthly_budget_usd=None,
        ),
        "env_fallback",
    )


# ── CRUD helpers (usados por los routes) ───────────────────────────────


async def create_byok_key(
    tenant_id: UUID,
    user_id: UUID,
    scope_type: str,
    scope_id: UUID | None,
    provider: str,
    plaintext_value: str,
    monthly_budget_usd: float | None = None,
) -> dict[str, Any]:
    """Crea una key. NO valida contra el provider (eso lo hace el endpoint).

    Encripta el plaintext con la master key y persiste. El plaintext queda
    como `[redacted]` en logs; solo `fingerprint_last4` es seguro de loguear.
    """
    if scope_type not in ("tenant", "facultad", "materia"):
        raise ValueError(f"scope_type invalido: {scope_type!r}")
    if scope_type == "tenant" and scope_id is not None:
        raise ValueError("scope_type=tenant requiere scope_id=None")
    if scope_type in ("facultad", "materia") and scope_id is None:
        raise ValueError(f"scope_type={scope_type} requiere scope_id NOT NULL")
    if provider not in ("anthropic", "gemini", "mistral", "openai"):
        raise ValueError(f"provider invalido: {provider!r}")
    if len(plaintext_value) < 8:
        raise ValueError("plaintext_value demasiado corto (probablemente invalido)")

    master_key = _get_master_key_bytes()
    if master_key is None:
        raise ValueError(
            "BYOK_MASTER_KEY no configurada — no se pueden crear keys encriptadas"
        )

    from platform_ops.crypto import encrypt

    encrypted = encrypt(plaintext_value.encode("utf-8"), master_key)
    fingerprint = plaintext_value[-4:]

    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)
        key = BYOKKey(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            provider=provider,
            encrypted_value=encrypted,
            fingerprint_last4=fingerprint,
            monthly_budget_usd=monthly_budget_usd,
            created_by=user_id,
        )
        session.add(key)
        await session.commit()
        # `set_config(..., is_local=true)` se resetea con commit; reaplicamos
        # antes de cualquier SELECT (refresh) para que RLS no bloquee la
        # lectura del row recien creado.
        await _set_tenant_rls(session, tenant_id)
        await session.refresh(key)
        return _key_to_dict(key)


async def list_byok_keys(
    tenant_id: UUID,
    scope_type: str | None = None,
    scope_id: UUID | None = None,
) -> list[dict[str, Any]]:
    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)
        stmt = select(BYOKKey).where(BYOKKey.tenant_id == tenant_id)
        if scope_type is not None:
            stmt = stmt.where(BYOKKey.scope_type == scope_type)
        if scope_id is not None:
            stmt = stmt.where(BYOKKey.scope_id == scope_id)
        rows = (await session.execute(stmt.order_by(BYOKKey.created_at.desc()))).scalars().all()
        return [_key_to_dict(r) for r in rows]


async def rotate_byok_key(
    tenant_id: UUID,
    key_id: UUID,
    new_plaintext_value: str,
) -> dict[str, Any] | None:
    """Rota el plaintext de una key existente.

    Sec 7.3 epic ai-native-completion-and-byok. Re-encripta el nuevo plaintext
    con la master key vigente y sustituye `encrypted_value` + `fingerprint_last4`.
    Preserva `id`, `scope`, `created_at`, `created_by` — la rotacion es
    transparente para el resolver y los callers que ya tenian el `key_id`.

    NO se permite rotar una key revocada (404 — el caller debe crear una nueva).

    Args:
        tenant_id: tenant del que se ejerce la rotacion (filtrado RLS).
        key_id: identificador de la key existente.
        new_plaintext_value: el nuevo secreto en plaintext (se encripta y descarta).

    Returns:
        El dict serializado de la key (sin plaintext, sin encrypted_value)
        si la rotacion fue exitosa, o None si la key no existe / esta revocada.

    Raises:
        ValueError: si BYOK_MASTER_KEY no esta configurada o el plaintext
            es demasiado corto.
    """
    if len(new_plaintext_value) < 8:
        raise ValueError("plaintext_value demasiado corto (probablemente invalido)")

    master_key = _get_master_key_bytes()
    if master_key is None:
        raise ValueError(
            "BYOK_MASTER_KEY no configurada — no se pueden rotar keys encriptadas"
        )

    from platform_ops.crypto import encrypt

    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)
        row = await session.get(BYOKKey, key_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        if row.revoked_at is not None:
            return None  # key revocada — caller debe crear una nueva
        row.encrypted_value = encrypt(new_plaintext_value.encode("utf-8"), master_key)
        row.fingerprint_last4 = new_plaintext_value[-4:]
        await session.commit()
        await _set_tenant_rls(session, tenant_id)
        await session.refresh(row)
        return _key_to_dict(row)


async def revoke_byok_key(tenant_id: UUID, key_id: UUID) -> dict[str, Any] | None:
    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)
        row = await session.get(BYOKKey, key_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            await session.commit()
            await _set_tenant_rls(session, tenant_id)
            await session.refresh(row)
        return _key_to_dict(row)


async def increment_usage(
    tenant_id: UUID,
    key_id: UUID,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
) -> None:
    """Incrementa contadores de uso de una BYOK key (audit trail por mes).

    Se llama desde el endpoint /complete (y /stream) después de que el
    LLM responde, cuando `resolved.key_id is not None` (o sea, NO env_fallback).
    UPSERT por PK compuesta (key_id, yyyymm).

    También actualiza `last_used_at` en `byok_keys` para que admin vea
    cuándo fue la última vez que se usó cada key.

    Idempotencia: el ON CONFLICT garantiza que dos calls concurrentes
    al mismo (key_id, yyyymm) suman correctamente sin duplicar.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(UTC)
    yyyymm = f"{now.year:04d}{now.month:02d}"
    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)

        # UPSERT en byok_keys_usage
        stmt = (
            pg_insert(BYOKKeyUsage)
            .values(
                key_id=key_id,
                yyyymm=yyyymm,
                tenant_id=tenant_id,
                tokens_input_total=tokens_input,
                tokens_output_total=tokens_output,
                cost_usd_total=cost_usd,
                request_count=1,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["key_id", "yyyymm"],
                set_={
                    "tokens_input_total": BYOKKeyUsage.__table__.c.tokens_input_total
                    + tokens_input,
                    "tokens_output_total": BYOKKeyUsage.__table__.c.tokens_output_total
                    + tokens_output,
                    "cost_usd_total": BYOKKeyUsage.__table__.c.cost_usd_total + cost_usd,
                    "request_count": BYOKKeyUsage.__table__.c.request_count + 1,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)

        # Actualizar last_used_at en la key
        from sqlalchemy import update

        await session.execute(
            update(BYOKKey).where(BYOKKey.id == key_id).values(last_used_at=now)
        )

        await session.commit()


# ── env_fallback usage tracking (gap auditoría doctoral 2026-05-07) ────
#
# La tabla `byok_keys_usage` tiene `key_id` como PK + FK NOT NULL a
# `byok_keys.id` (ondelete CASCADE). Para registrar uso del env_fallback
# (cuando el docente NO tiene key BYOK propia y el ai-gateway cae a la key
# global del env), seguimos la **Opción B**: insertamos una BYOKKey
# **sintética por (tenant_id, provider)** con id determinista (UUID v5) y
# acumulamos usage contra ella. Detalles del diseño:
#
# 1. UUID v5 determinista (namespace estable + nombre `tenant_id|provider`)
#    => idempotencia: el mismo tenant+provider siempre apunta al mismo id.
# 2. La sentinel se crea con `scope_type='tenant'` + `scope_id=NULL`
#    (satisface CHECK `ck_byok_scope_type` y `ck_byok_scope_id_consistency`).
# 3. `revoked_at` se setea a `created_at` para que **NUNCA** matchee el
#    UNIQUE parcial `uq_byok_keys_active` (que filtra `revoked_at IS NULL`).
#    => no choca con la BYOK real del docente y el resolver nunca la elige
#    (todos los SELECT del resolver filtran `revoked_at.is_(None)`).
# 4. `encrypted_value` queda en `b""` — la sentinel NO se desencripta
#    nunca; es un row de catálogo solo para satisfacer la FK.
# 5. `fingerprint_last4='ENVF'` para identificarla en queries de auditoría.
# 6. `created_by` se setea al UUID nil (`00000000-...`) — no hay user real.
#
# Esto permite a la auditoría doctoral hacer:
#   SELECT * FROM byok_keys_usage u JOIN byok_keys k ON u.key_id=k.id
#   WHERE k.fingerprint_last4='ENVF';
# para obtener el costo total cubierto por el env global del piloto.

# Namespace UUID v5 estable para sentinels env_fallback. NO cambiar — un
# nuevo namespace re-genera todos los ids y orfana las rows existentes.
_ENV_FALLBACK_UUID_NAMESPACE = UUID("e0fa11ba-c000-5000-a000-000000000000")
_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


def _synthetic_env_fallback_key_id(tenant_id: UUID, provider: str) -> UUID:
    """UUID v5 determinista por (tenant, provider). Mismo input → mismo id."""
    return uuid5(_ENV_FALLBACK_UUID_NAMESPACE, f"{tenant_id}|{provider}")


async def _ensure_env_fallback_sentinel(
    session: AsyncSession, tenant_id: UUID, provider: str
) -> UUID:
    """Garantiza la BYOKKey sentinel para (tenant, provider). Idempotente.

    Si no existe, INSERT con `revoked_at=created_at` para que NUNCA matchee
    el UNIQUE parcial activo (no choca con la BYOK real del docente). Si ya
    existe, no-op.

    Devuelve el `id` de la sentinel — usable como FK en `byok_keys_usage`.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    sentinel_id = _synthetic_env_fallback_key_id(tenant_id, provider)
    now = datetime.now(UTC)
    stmt = (
        pg_insert(BYOKKey)
        .values(
            id=sentinel_id,
            tenant_id=tenant_id,
            scope_type="tenant",
            scope_id=None,
            provider=provider,
            encrypted_value=b"",  # placeholder — nunca se desencripta
            fingerprint_last4="ENVF",
            monthly_budget_usd=None,
            created_at=now,
            created_by=_NIL_UUID,
            revoked_at=now,  # CRITICO: queda fuera del UNIQUE parcial activo
            last_used_at=None,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    return sentinel_id


async def increment_env_fallback_usage(
    tenant_id: UUID,
    provider: str,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
) -> UUID:
    """Incrementa contadores de uso cuando el resolver cayó a env_fallback.

    Audit trail doctoral (gap 2026-05-07): cuando el docente NO tiene key
    BYOK propia y el ai-gateway usa la key global del env, igual queremos
    registrar el costo en `byok_keys_usage` para auditoría académica.
    Insertamos contra una BYOKKey sentinel determinista por (tenant, provider)
    — ver docstring de `_ensure_env_fallback_sentinel`.

    UPSERT por PK compuesta `(key_id, yyyymm)`. Idempotente bajo concurrencia.

    Devuelve el `key_id` de la sentinel usada (útil para tests y debug).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(UTC)
    yyyymm = f"{now.year:04d}{now.month:02d}"
    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)

        sentinel_id = await _ensure_env_fallback_sentinel(session, tenant_id, provider)

        stmt = (
            pg_insert(BYOKKeyUsage)
            .values(
                key_id=sentinel_id,
                yyyymm=yyyymm,
                tenant_id=tenant_id,
                tokens_input_total=tokens_input,
                tokens_output_total=tokens_output,
                cost_usd_total=cost_usd,
                request_count=1,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["key_id", "yyyymm"],
                set_={
                    "tokens_input_total": BYOKKeyUsage.__table__.c.tokens_input_total
                    + tokens_input,
                    "tokens_output_total": BYOKKeyUsage.__table__.c.tokens_output_total
                    + tokens_output,
                    "cost_usd_total": BYOKKeyUsage.__table__.c.cost_usd_total + cost_usd,
                    "request_count": BYOKKeyUsage.__table__.c.request_count + 1,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
        return sentinel_id


async def get_byok_key_usage(
    tenant_id: UUID, key_id: UUID, yyyymm: str | None = None
) -> dict[str, Any]:
    if yyyymm is None:
        now = datetime.now(UTC)
        yyyymm = f"{now.year:04d}{now.month:02d}"
    sm = _get_sessionmaker()
    async with sm() as session:
        await _set_tenant_rls(session, tenant_id)
        row = await session.get(BYOKKeyUsage, (key_id, yyyymm))
        if row is None:
            return {
                "key_id": str(key_id),
                "yyyymm": yyyymm,
                "tokens_input_total": 0,
                "tokens_output_total": 0,
                "cost_usd_total": 0.0,
                "request_count": 0,
            }
        return {
            "key_id": str(row.key_id),
            "yyyymm": row.yyyymm,
            "tokens_input_total": int(row.tokens_input_total),
            "tokens_output_total": int(row.tokens_output_total),
            "cost_usd_total": float(row.cost_usd_total),
            "request_count": int(row.request_count),
        }


def _key_to_dict(k: BYOKKey) -> dict[str, Any]:
    """Serializa SIN exponer el encrypted_value (defensa de privacidad)."""
    return {
        "id": str(k.id),
        "tenant_id": str(k.tenant_id),
        "scope_type": k.scope_type,
        "scope_id": str(k.scope_id) if k.scope_id else None,
        "provider": k.provider,
        "fingerprint_last4": k.fingerprint_last4,
        "monthly_budget_usd": (
            float(k.monthly_budget_usd) if k.monthly_budget_usd is not None else None
        ),
        "created_at": k.created_at.isoformat(),
        "created_by": str(k.created_by),
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
    }
