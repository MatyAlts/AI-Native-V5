"""Tests del servicio BYOK (resolver jerarquico, encrypt/decrypt, CRUD).

Cubre `apps/ai-gateway/src/ai_gateway/services/byok.py`:
- `_get_master_key_bytes`: configuracion de master key (base64, length, etc).
- `_env_fallback_key`: fallback a env vars legacy por provider.
- `resolve_byok_key`: resolver jerarquico (materia -> tenant -> env_fallback).
- `create_byok_key`: validaciones de scope_type/scope_id, longitud minima.
- `rotate_byok_key`: validacion de plaintext, no-master-key.

Las DB calls se mockean — todos los tests son deterministas, sin red ni
contenedores.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from ai_gateway.services import byok as byok_module
from ai_gateway.services.byok import (
    BYOKKey,
    _env_fallback_key,
    _get_master_key_bytes,
    _key_to_dict,
    _synthetic_env_fallback_key_id,
    create_byok_key,
    get_byok_key_usage,
    increment_env_fallback_usage,
    list_byok_keys,
    resolve_byok_key,
    revoke_byok_key,
    rotate_byok_key,
)


# ── _get_master_key_bytes ──────────────────────────────────────────────


def test_master_key_vacia_devuelve_none(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "")
    assert _get_master_key_bytes() is None


def test_master_key_invalid_base64_devuelve_none(monkeypatch) -> None:
    # "!!!" no es base64 valido
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "!!!not_b64!!!")
    assert _get_master_key_bytes() is None


def test_master_key_wrong_size_devuelve_none(monkeypatch) -> None:
    # 16 bytes en lugar de 32
    short_key = base64.b64encode(b"\x00" * 16).decode()
    monkeypatch.setattr(byok_module.settings, "byok_master_key", short_key)
    assert _get_master_key_bytes() is None


def test_master_key_valida_devuelve_32_bytes(monkeypatch) -> None:
    valid_key = base64.b64encode(b"\xab" * 32).decode()
    monkeypatch.setattr(byok_module.settings, "byok_master_key", valid_key)
    result = _get_master_key_bytes()
    assert result is not None
    assert len(result) == 32
    assert result == b"\xab" * 32


# ── _env_fallback_key ──────────────────────────────────────────────────


def test_env_fallback_anthropic(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "sk-ant-xxx")
    assert _env_fallback_key("anthropic") == "sk-ant-xxx"


def test_env_fallback_openai(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "openai_api_key", "sk-oa-yyy")
    assert _env_fallback_key("openai") == "sk-oa-yyy"


def test_env_fallback_provider_desconocido_devuelve_none() -> None:
    assert _env_fallback_key("not-a-real-provider") is None


def test_env_fallback_vacia_devuelve_none(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "")
    assert _env_fallback_key("anthropic") is None


# ── resolve_byok_key: BYOK_ENABLED=False (early return) ────────────────


async def test_resolve_byok_disabled_con_env_fallback(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_enabled", False)
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "sk-fallback")

    result = await resolve_byok_key(uuid4(), "anthropic", materia_id=None)
    assert result is not None
    assert result.scope_resolved == "env_fallback"
    assert result.plaintext == "sk-fallback"
    assert result.key_id is None


async def test_resolve_byok_disabled_sin_env_devuelve_none(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_enabled", False)
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "")
    monkeypatch.setattr(byok_module.settings, "openai_api_key", "")
    monkeypatch.setattr(byok_module.settings, "gemini_api_key", "")
    monkeypatch.setattr(byok_module.settings, "mistral_api_key", "")

    result = await resolve_byok_key(uuid4(), "anthropic")
    assert result is None


# ── resolve_byok_key: BYOK_ENABLED=True con master key faltante ────────


async def test_resolve_sin_master_key_cae_a_env_fallback(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_enabled", True)
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "")  # No master
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "sk-env")

    result = await resolve_byok_key(uuid4(), "anthropic")
    assert result is not None
    assert result.scope_resolved == "env_fallback"
    assert result.plaintext == "sk-env"


async def test_resolve_sin_master_key_y_sin_env_devuelve_none(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_enabled", True)
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "")
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "")
    monkeypatch.setattr(byok_module.settings, "openai_api_key", "")
    monkeypatch.setattr(byok_module.settings, "gemini_api_key", "")
    monkeypatch.setattr(byok_module.settings, "mistral_api_key", "")

    result = await resolve_byok_key(uuid4(), "anthropic")
    assert result is None


# ── resolve_byok_key: hits en DB (materia / tenant) ────────────────────
#
# Para evitar tocar Postgres real, mockeamos el sessionmaker. El resolver
# llama session.execute(stmt) y obtiene `scalar_one_or_none()`.


def _setup_master_key(monkeypatch) -> bytes:
    raw = b"\x42" * 32
    monkeypatch.setattr(byok_module.settings, "byok_master_key", base64.b64encode(raw).decode())
    monkeypatch.setattr(byok_module.settings, "byok_enabled", True)
    return raw


def _build_mock_session(rows_by_call: list[Any]) -> tuple[Any, Any]:
    """Devuelve (sessionmaker_mock, session_mock).

    `rows_by_call` = lista de objetos a devolver en `scalar_one_or_none()`
    en sucesivos SELECTs (excluye el `SET LOCAL` que NO devuelve filas).

    Distingue entre statements via inspeccion del primer arg: si el SQL
    es un `text(...)` usado por `_set_tenant_rls`, devolvemos un mock
    vacio. Si es un Select, consumimos el siguiente elemento de la cola.
    """
    session_mock = AsyncMock()

    rows_iter = iter(rows_by_call)

    async def _execute(stmt, params=None, *args, **kwargs):
        # `_set_tenant_rls` usa `text("SELECT set_config(...)")` con bind
        # params. Lo distinguimos por la presencia de un dict `params` con
        # el bind `tid`.
        if params is not None and isinstance(params, dict) and "tid" in params:
            empty = MagicMock()
            empty.scalar_one_or_none = MagicMock(return_value=None)
            return empty
        try:
            row = next(rows_iter)
        except StopIteration:
            row = None
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        return result

    session_mock.execute = AsyncMock(side_effect=_execute)

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm_callable = MagicMock(side_effect=lambda: _ctx())
    return sm_callable, session_mock


def _make_byok_row(
    *, scope_type: str, scope_id: UUID | None, encrypted: bytes, budget: float | None = None
) -> BYOKKey:
    row = BYOKKey()
    row.id = uuid4()
    row.tenant_id = uuid4()
    row.scope_type = scope_type
    row.scope_id = scope_id
    row.provider = "anthropic"
    row.encrypted_value = encrypted
    row.fingerprint_last4 = "abcd"
    row.monthly_budget_usd = budget
    row.created_at = datetime.now(UTC)
    row.created_by = uuid4()
    row.revoked_at = None
    row.last_used_at = None
    return row


async def test_resolve_hit_en_materia(monkeypatch) -> None:
    raw_key = _setup_master_key(monkeypatch)
    from platform_ops.crypto import encrypt

    plaintext = "sk-materia-key"
    encrypted = encrypt(plaintext.encode(), raw_key)
    materia_id = uuid4()
    tenant_id = uuid4()

    row = _make_byok_row(
        scope_type="materia", scope_id=materia_id, encrypted=encrypted, budget=50.0
    )
    sm, _ = _build_mock_session([row])
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await resolve_byok_key(tenant_id, "anthropic", materia_id=materia_id)
    assert result is not None
    assert result.scope_resolved == "materia"
    assert result.plaintext == plaintext
    assert result.monthly_budget_usd == 50.0
    assert result.key_id == row.id


async def test_resolve_miss_materia_hit_tenant(monkeypatch) -> None:
    raw_key = _setup_master_key(monkeypatch)
    from platform_ops.crypto import encrypt

    plaintext = "sk-tenant-key"
    encrypted = encrypt(plaintext.encode(), raw_key)
    tenant_id = uuid4()
    materia_id = uuid4()

    # Resolver jerarquico (ADR-039): materia -> facultad -> tenant.
    # Primera call (materia) miss; segunda (facultad) miss; tercera (tenant) hit.
    tenant_row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=encrypted)
    sm, _ = _build_mock_session([None, None, tenant_row])
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await resolve_byok_key(tenant_id, "anthropic", materia_id=materia_id)
    assert result is not None
    assert result.scope_resolved == "tenant"
    assert result.plaintext == plaintext


async def test_resolve_miss_materia_y_tenant_fallback_env(monkeypatch) -> None:
    _setup_master_key(monkeypatch)
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "sk-env-tail")

    # Resolver jerarquico: materia -> facultad -> tenant -> env_fallback.
    sm, _ = _build_mock_session([None, None, None])  # tres niveles miss
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await resolve_byok_key(uuid4(), "anthropic", materia_id=uuid4())
    assert result is not None
    assert result.scope_resolved == "env_fallback"
    assert result.plaintext == "sk-env-tail"


async def test_resolve_sin_materia_id_va_directo_a_tenant(monkeypatch) -> None:
    raw_key = _setup_master_key(monkeypatch)
    from platform_ops.crypto import encrypt

    encrypted = encrypt(b"sk-direct-tenant", raw_key)
    tenant_row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=encrypted)
    # materia_id=None salta el query de materia. Quedan: facultad miss + tenant hit.
    sm, session_mock = _build_mock_session([None, tenant_row])
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await resolve_byok_key(uuid4(), "anthropic", materia_id=None)
    assert result is not None
    assert result.scope_resolved == "tenant"
    # 1 SET LOCAL + 1 SELECT facultad + 1 SELECT tenant = 3.
    # SI hubiera intentado materia, serian 4.
    assert session_mock.execute.call_count == 3


async def test_resolve_decrypt_fallido_cae_a_env(monkeypatch) -> None:
    """Si la decriptacion falla (master key cambio post-encrypt), hace fallback."""
    _setup_master_key(monkeypatch)
    monkeypatch.setattr(byok_module.settings, "anthropic_api_key", "sk-env-after-decrypt-fail")

    # Encrypted bytes invalidos — al desencriptar tira CryptoError
    bad_encrypted = b"\x00" * 30
    bad_row = _make_byok_row(scope_type="materia", scope_id=uuid4(), encrypted=bad_encrypted)
    # fila materia (decrypt fail), facultad miss, tenant miss
    sm, _ = _build_mock_session([bad_row, None, None])
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await resolve_byok_key(uuid4(), "anthropic", materia_id=bad_row.scope_id)
    # Como decrypt fallo en materia y miss en facultad/tenant, fallback a env
    assert result is not None
    assert result.scope_resolved == "env_fallback"


# ── create_byok_key: validaciones de input ─────────────────────────────


async def test_create_scope_type_invalido_raise() -> None:
    with pytest.raises(ValueError, match="scope_type invalido"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="planeta",  # invalido
            scope_id=None,
            provider="anthropic",
            plaintext_value="sk-ant-1234567890",
        )


async def test_create_scope_tenant_con_scope_id_raise() -> None:
    with pytest.raises(ValueError, match="scope_type=tenant requiere scope_id=None"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="tenant",
            scope_id=uuid4(),  # incompatible
            provider="anthropic",
            plaintext_value="sk-ant-1234567890",
        )


async def test_create_scope_materia_sin_scope_id_raise() -> None:
    with pytest.raises(ValueError, match="requiere scope_id NOT NULL"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="materia",
            scope_id=None,
            provider="anthropic",
            plaintext_value="sk-ant-1234567890",
        )


async def test_create_provider_invalido_raise() -> None:
    with pytest.raises(ValueError, match="provider invalido"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="tenant",
            scope_id=None,
            provider="claude-direct",  # no es provider valido
            plaintext_value="sk-ant-1234567890",
        )


async def test_create_plaintext_corto_raise() -> None:
    with pytest.raises(ValueError, match="demasiado corto"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="tenant",
            scope_id=None,
            provider="anthropic",
            plaintext_value="abc",  # <8 chars
        )


async def test_create_sin_master_key_raise(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "")
    with pytest.raises(ValueError, match="BYOK_MASTER_KEY"):
        await create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="tenant",
            scope_id=None,
            provider="anthropic",
            plaintext_value="sk-ant-validkey-12345",
        )


async def test_create_happy_path_persiste_key(monkeypatch) -> None:
    """Mockea sessionmaker y verifica que se construye un BYOKKey valido."""
    _setup_master_key(monkeypatch)

    captured: dict[str, Any] = {}
    session_mock = AsyncMock()
    session_mock.commit = AsyncMock()

    def _add(obj: Any) -> None:
        captured["key"] = obj

    async def _refresh(obj: Any) -> None:
        # Simula que la DB poblo defaults del modelo (created_at, id).
        if obj.created_at is None:
            obj.created_at = datetime.now(UTC)
        if obj.id is None:
            obj.id = uuid4()

    session_mock.refresh = AsyncMock(side_effect=_refresh)
    session_mock.add = MagicMock(side_effect=_add)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    tenant_id = uuid4()
    user_id = uuid4()
    result = await create_byok_key(
        tenant_id=tenant_id,
        user_id=user_id,
        scope_type="tenant",
        scope_id=None,
        provider="anthropic",
        plaintext_value="sk-ant-secretvalue1234",
        monthly_budget_usd=42.5,
    )
    assert result["scope_type"] == "tenant"
    assert result["provider"] == "anthropic"
    assert result["fingerprint_last4"] == "1234"
    assert result["monthly_budget_usd"] == 42.5
    # encrypted_value NO debe aparecer en el dict
    assert "encrypted_value" not in result

    # La row fue agregada
    assert "key" in captured
    row = captured["key"]
    assert row.scope_type == "tenant"
    assert row.scope_id is None
    assert row.fingerprint_last4 == "1234"


# ── rotate_byok_key ────────────────────────────────────────────────────


async def test_rotate_plaintext_corto_raise(monkeypatch) -> None:
    _setup_master_key(monkeypatch)
    with pytest.raises(ValueError, match="demasiado corto"):
        await rotate_byok_key(uuid4(), uuid4(), "abc")


async def test_rotate_sin_master_key_raise(monkeypatch) -> None:
    monkeypatch.setattr(byok_module.settings, "byok_master_key", "")
    with pytest.raises(ValueError, match="BYOK_MASTER_KEY"):
        await rotate_byok_key(uuid4(), uuid4(), "sk-validplaintext-99")


async def test_rotate_key_no_existe_devuelve_none(monkeypatch) -> None:
    _setup_master_key(monkeypatch)
    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=None)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await rotate_byok_key(uuid4(), uuid4(), "sk-newvaluekey-xyz")
    assert result is None


async def test_rotate_key_revocada_devuelve_none(monkeypatch) -> None:
    _setup_master_key(monkeypatch)
    tenant_id = uuid4()
    revoked = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    revoked.tenant_id = tenant_id
    revoked.revoked_at = datetime.now(UTC)

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=revoked)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await rotate_byok_key(tenant_id, revoked.id, "sk-rotatevalue-zzz")
    assert result is None


async def test_rotate_tenant_distinto_devuelve_none(monkeypatch) -> None:
    """Defensa cross-tenant: si el row.tenant_id no matchea, no rota."""
    _setup_master_key(monkeypatch)
    other_tenant = uuid4()
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    row.tenant_id = other_tenant  # NO el tenant del caller

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=row)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await rotate_byok_key(uuid4(), row.id, "sk-other-tenantattempt")
    assert result is None


async def test_rotate_happy_path_actualiza_fingerprint(monkeypatch) -> None:
    raw = _setup_master_key(monkeypatch)
    tenant_id = uuid4()
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    row.tenant_id = tenant_id
    row.fingerprint_last4 = "OLD_"  # 4 chars dummy

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=row)
    session_mock.commit = AsyncMock()
    session_mock.refresh = AsyncMock()
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    new_pt = "sk-newrotated-value-WXYZ"
    result = await rotate_byok_key(tenant_id, row.id, new_pt)
    assert result is not None
    assert result["fingerprint_last4"] == "WXYZ"
    # encrypted_value se cambio in-place
    assert row.encrypted_value != b"\x00" * 32
    assert row.fingerprint_last4 == "WXYZ"

    # Roundtrip: el nuevo encrypted decifra al new_pt
    from platform_ops.crypto import decrypt

    assert decrypt(row.encrypted_value, raw).decode() == new_pt


# ── revoke_byok_key ────────────────────────────────────────────────────


async def test_revoke_no_existe_devuelve_none(monkeypatch) -> None:
    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=None)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await revoke_byok_key(uuid4(), uuid4())
    assert result is None


async def test_revoke_setea_revoked_at(monkeypatch) -> None:
    tenant_id = uuid4()
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    row.tenant_id = tenant_id
    assert row.revoked_at is None

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=row)
    session_mock.commit = AsyncMock()
    session_mock.refresh = AsyncMock()
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await revoke_byok_key(tenant_id, row.id)
    assert result is not None
    assert row.revoked_at is not None
    assert result["revoked_at"] is not None


async def test_revoke_idempotente(monkeypatch) -> None:
    """Doble revoke no rompe — devuelve la key con revoked_at original."""
    tenant_id = uuid4()
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    row.tenant_id = tenant_id
    row.revoked_at = earlier

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=row)
    session_mock.commit = AsyncMock()
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await revoke_byok_key(tenant_id, row.id)
    assert result is not None
    # No cambio el revoked_at — mantuvo el original
    assert row.revoked_at == earlier


async def test_revoke_cross_tenant_devuelve_none(monkeypatch) -> None:
    other = uuid4()
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    row.tenant_id = other

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=row)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await revoke_byok_key(uuid4(), row.id)
    assert result is None


# ── list_byok_keys ─────────────────────────────────────────────────────


async def test_list_devuelve_lista_vacia_si_no_hay(monkeypatch) -> None:
    session_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars = MagicMock(return_value=MagicMock(all=lambda: []))
    session_mock.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await list_byok_keys(uuid4())
    assert result == []


async def test_list_filtra_por_scope_type(monkeypatch) -> None:
    row1 = _make_byok_row(scope_type="materia", scope_id=uuid4(), encrypted=b"\x00" * 32)
    session_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars = MagicMock(return_value=MagicMock(all=lambda: [row1]))
    session_mock.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await list_byok_keys(uuid4(), scope_type="materia", scope_id=row1.scope_id)
    assert len(result) == 1
    assert result[0]["scope_type"] == "materia"


# ── get_byok_key_usage ─────────────────────────────────────────────────


async def test_usage_no_existe_devuelve_zeros(monkeypatch) -> None:
    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=None)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    key_id = uuid4()
    result = await get_byok_key_usage(uuid4(), key_id, yyyymm="202605")
    assert result["key_id"] == str(key_id)
    assert result["yyyymm"] == "202605"
    assert result["tokens_input_total"] == 0
    assert result["tokens_output_total"] == 0
    assert result["cost_usd_total"] == 0.0
    assert result["request_count"] == 0


async def test_usage_default_yyyymm_es_mes_actual(monkeypatch) -> None:
    """Si yyyymm=None, computa el mes actual en formato YYYYMM."""
    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=None)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await get_byok_key_usage(uuid4(), uuid4())
    now = datetime.now(UTC)
    expected = f"{now.year:04d}{now.month:02d}"
    assert result["yyyymm"] == expected


async def test_usage_existente_devuelve_totales(monkeypatch) -> None:
    from ai_gateway.services.byok import BYOKKeyUsage

    usage_row = BYOKKeyUsage()
    usage_row.key_id = uuid4()
    usage_row.yyyymm = "202604"
    usage_row.tenant_id = uuid4()
    usage_row.tokens_input_total = 1000
    usage_row.tokens_output_total = 500
    usage_row.cost_usd_total = 0.42
    usage_row.request_count = 7
    usage_row.updated_at = datetime.now(UTC)

    session_mock = AsyncMock()
    session_mock.get = AsyncMock(return_value=usage_row)
    session_mock.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    result = await get_byok_key_usage(uuid4(), usage_row.key_id, yyyymm="202604")
    assert result["tokens_input_total"] == 1000
    assert result["tokens_output_total"] == 500
    assert result["cost_usd_total"] == pytest.approx(0.42)
    assert result["request_count"] == 7


# ── _key_to_dict serialization ─────────────────────────────────────────


def test_key_to_dict_no_expone_encrypted_value() -> None:
    row = _make_byok_row(
        scope_type="materia", scope_id=uuid4(), encrypted=b"SECRET_BYTES" * 4
    )
    out = _key_to_dict(row)
    assert "encrypted_value" not in out
    # Tampoco aparece como bytes en ningun campo serializado
    for v in out.values():
        if isinstance(v, str):
            assert "SECRET_BYTES" not in v


def test_key_to_dict_serializa_scope_id_none() -> None:
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    out = _key_to_dict(row)
    assert out["scope_id"] is None


def test_key_to_dict_serializa_revoked_at_none() -> None:
    row = _make_byok_row(scope_type="tenant", scope_id=None, encrypted=b"\x00" * 32)
    assert row.revoked_at is None
    out = _key_to_dict(row)
    assert out["revoked_at"] is None
    assert out["last_used_at"] is None


# ── env_fallback usage tracking (gap auditoria doctoral 2026-05-07) ────


def test_synthetic_env_fallback_id_es_determinista() -> None:
    """Mismo (tenant, provider) => mismo UUID v5."""
    tenant = uuid4()
    a = _synthetic_env_fallback_key_id(tenant, "anthropic")
    b = _synthetic_env_fallback_key_id(tenant, "anthropic")
    assert a == b


def test_synthetic_env_fallback_id_distinto_por_provider() -> None:
    tenant = uuid4()
    a = _synthetic_env_fallback_key_id(tenant, "anthropic")
    b = _synthetic_env_fallback_key_id(tenant, "openai")
    assert a != b


def test_synthetic_env_fallback_id_distinto_por_tenant() -> None:
    a = _synthetic_env_fallback_key_id(uuid4(), "anthropic")
    b = _synthetic_env_fallback_key_id(uuid4(), "anthropic")
    assert a != b


async def test_increment_env_fallback_usage_inserta_sentinel_y_usage(
    monkeypatch,
) -> None:
    """Cuando el resolver cae a env_fallback, increment_env_fallback_usage
    debe (1) ensure-sentinel BYOKKey por (tenant, provider) y (2) UPSERT
    en byok_keys_usage contra esa sentinel.

    Verificamos via mock que se ejecutaron exactamente 2 INSERTs (sentinel
    + usage) y que el sentinel_id devuelto coincide con el determinista.
    """
    executed_stmts: list[Any] = []

    async def _execute(stmt, params=None, *args, **kwargs):
        # _set_tenant_rls usa text() con bind params dict que incluye 'tid'
        if params is not None and isinstance(params, dict) and "tid" in params:
            return MagicMock()
        executed_stmts.append(stmt)
        return MagicMock()

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(side_effect=_execute)
    session_mock.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    tenant_id = uuid4()
    sentinel_id = await increment_env_fallback_usage(
        tenant_id=tenant_id,
        provider="anthropic",
        tokens_input=120,
        tokens_output=45,
        cost_usd=0.01234,
    )

    # ID devuelto coincide con el determinista
    assert sentinel_id == _synthetic_env_fallback_key_id(tenant_id, "anthropic")

    # Se ejecutaron exactamente 2 INSERT statements (excluyendo el SET LOCAL)
    assert len(executed_stmts) == 2

    # El commit fue llamado exactamente una vez al final
    session_mock.commit.assert_awaited_once()


async def test_increment_env_fallback_usage_idempotente_misma_sentinel(
    monkeypatch,
) -> None:
    """Dos calls al mismo (tenant, provider) usan la MISMA sentinel.

    El ON CONFLICT DO NOTHING en la sentinel + ON CONFLICT DO UPDATE en el
    usage garantizan idempotencia: el segundo call NO crea una sentinel
    nueva y SI acumula contadores en la usage row existente.
    """
    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(return_value=MagicMock())
    session_mock.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    tenant = uuid4()
    id1 = await increment_env_fallback_usage(tenant, "anthropic", 10, 5, 0.001)
    id2 = await increment_env_fallback_usage(tenant, "anthropic", 20, 10, 0.002)

    assert id1 == id2  # determinismo


async def test_increment_env_fallback_usage_distinto_provider_distinto_id(
    monkeypatch,
) -> None:
    """Mismo tenant pero provider distinto => sentinels independientes."""
    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(return_value=MagicMock())
    session_mock.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    sm = MagicMock(side_effect=lambda: _ctx())
    monkeypatch.setattr(byok_module, "_get_sessionmaker", lambda: sm)

    tenant = uuid4()
    id_anthropic = await increment_env_fallback_usage(tenant, "anthropic", 1, 1, 0.0)
    id_openai = await increment_env_fallback_usage(tenant, "openai", 1, 1, 0.0)

    assert id_anthropic != id_openai
