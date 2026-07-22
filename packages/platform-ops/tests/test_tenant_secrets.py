"""Tests del resolver de secrets por tenant."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from platform_ops.tenant_secrets import (
    SecretNotFoundError,
    TenantSecretConfig,
    TenantSecretResolver,
)


@pytest.fixture
def tenant_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def resolver(tmp_path: Path) -> TenantSecretResolver:
    config = TenantSecretConfig(secrets_dir=str(tmp_path / "secrets"))
    return TenantSecretResolver(config)


# ── Mount de archivo por tenant (patrón K8s) ───────────────────────────


def test_lee_key_desde_archivo_mountado(
    resolver: TenantSecretResolver, tenant_id: UUID, tmp_path: Path
) -> None:
    key_dir = tmp_path / "secrets" / str(tenant_id)
    key_dir.mkdir(parents=True)
    (key_dir / "anthropic.key").write_text("sk-ant-tenant-specific-xyz")

    key = resolver.get_llm_api_key(tenant_id, "anthropic")
    assert key == "sk-ant-tenant-specific-xyz"


def test_archivo_vacio_no_cuenta_como_key(
    resolver: TenantSecretResolver, tenant_id: UUID, tmp_path: Path, monkeypatch
) -> None:
    """Un archivo vacío o con solo whitespace no debe tratarse como key válida."""
    key_dir = tmp_path / "secrets" / str(tenant_id)
    key_dir.mkdir(parents=True)
    (key_dir / "anthropic.key").write_text("   \n  \n")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SecretNotFoundError):
        resolver.get_llm_api_key(tenant_id, "anthropic")


# ── Env var por tenant ────────────────────────────────────────────────


def test_lee_key_desde_env_var_por_tenant(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    monkeypatch.setenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", "sk-env-per-tenant")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    key = resolver.get_llm_api_key(tenant_id, "anthropic")
    assert key == "sk-env-per-tenant"


# ── Fallback global ───────────────────────────────────────────────────


def test_usa_key_global_si_tenant_no_tiene(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    # Sin archivo ni env por tenant, solo global
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-global")
    monkeypatch.delenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", raising=False)

    key = resolver.get_llm_api_key(tenant_id, "anthropic")
    assert key == "sk-ant-global"


def test_key_especifica_del_tenant_pisa_global(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    """Si hay ambas, la del tenant gana."""
    monkeypatch.setenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", "sk-tenant-specific")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global-backup")

    key = resolver.get_llm_api_key(tenant_id, "anthropic")
    assert key == "sk-tenant-specific"


# ── Error cuando no hay ninguna ────────────────────────────────────────


def test_sin_ninguna_key_levanta_error_claro(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    monkeypatch.delenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(SecretNotFoundError) as exc_info:
        resolver.get_llm_api_key(tenant_id, "anthropic")

    msg = str(exc_info.value)
    assert str(tenant_id) in msg
    assert "anthropic" in msg
    assert "Configurar" in msg or "configurar" in msg


# ── Aislamiento entre tenants ──────────────────────────────────────────


def test_keys_de_distintos_tenants_son_independientes(
    resolver: TenantSecretResolver, monkeypatch
) -> None:
    t_a = uuid4()
    t_b = uuid4()
    monkeypatch.setenv(f"LLM_KEY_{t_a}_ANTHROPIC", "sk-tenant-a")
    monkeypatch.setenv(f"LLM_KEY_{t_b}_ANTHROPIC", "sk-tenant-b")

    assert resolver.get_llm_api_key(t_a, "anthropic") == "sk-tenant-a"
    assert resolver.get_llm_api_key(t_b, "anthropic") == "sk-tenant-b"


def test_has_tenant_specific_distingue_mount_vs_global(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global")
    monkeypatch.delenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", raising=False)

    # Sin mount ni env per-tenant, solo global → False
    assert not resolver.has_tenant_specific_key(tenant_id, "anthropic")

    monkeypatch.setenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", "sk-tenant")
    assert resolver.has_tenant_specific_key(tenant_id, "anthropic")


# ── Multi-provider ────────────────────────────────────────────────────


def test_providers_distintos_tienen_keys_distintas(
    resolver: TenantSecretResolver, tenant_id: UUID, monkeypatch
) -> None:
    monkeypatch.setenv(f"LLM_KEY_{tenant_id}_ANTHROPIC", "sk-ant")
    monkeypatch.setenv(f"LLM_KEY_{tenant_id}_OPENAI", "sk-oai")

    assert resolver.get_llm_api_key(tenant_id, "anthropic") == "sk-ant"
    assert resolver.get_llm_api_key(tenant_id, "openai") == "sk-oai"
