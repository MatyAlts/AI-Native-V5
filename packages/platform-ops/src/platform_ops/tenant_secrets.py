"""Resolución de secrets por tenant.

Permite que cada tenant tenga su propia API key del LLM provider
(Anthropic/OpenAI). La key se lee desde un secret store — en producción
K8s Secrets o Vault; en dev, env vars. Si el tenant no tiene key propia,
se usa la global de la plataforma (fallback).

Orden de resolución:
  1. `SECRET_{TENANT_ID}_ANTHROPIC_API_KEY` (env var por tenant)
  2. `ANTHROPIC_API_KEY` (global fallback)
  3. None → error claro

Design note: el ai-gateway NO persiste API keys en DB. Solo las resuelve
en memoria por request. La rotación es tan simple como cambiar el env
var y restart.

Para K8s, el patrón recomendado es mount de Secret con archivos por
tenant bajo /etc/platform/llm-keys/{tenant_id}/{provider}.key.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantSecretConfig:
    """Config del resolver de secrets."""

    # Dir donde están montados los secrets como archivos (K8s pattern).
    # Ej /etc/platform/llm-keys/{tenant_id}/anthropic.key
    secrets_dir: str = "/etc/platform/llm-keys"

    # Env vars fallback para dev local (sin secret mount)
    env_prefix_per_tenant: str = "LLM_KEY_"  # LLM_KEY_{UUID}_{PROVIDER}
    env_global_var_by_provider: dict[str, str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.env_global_var_by_provider is None:
            object.__setattr__(
                self,
                "env_global_var_by_provider",
                {
                    "anthropic": "ANTHROPIC_API_KEY",
                    "openai": "OPENAI_API_KEY",
                },
            )


class SecretNotFoundError(Exception):
    """Levantado cuando no se encuentra una key para (tenant, provider)."""


class TenantSecretResolver:
    """Resuelve secrets por (tenant_id, provider)."""

    def __init__(self, config: TenantSecretConfig | None = None) -> None:
        self.config = config or TenantSecretConfig()

    def get_llm_api_key(self, tenant_id: UUID, provider: str = "anthropic") -> str:
        """Devuelve la API key para el tenant + provider dados.

        Raises:
            SecretNotFoundError si no hay key propia del tenant NI global.
        """
        provider = provider.lower()

        # 1. Secret mount por tenant (K8s)
        key_path = Path(self.config.secrets_dir) / str(tenant_id) / f"{provider}.key"
        if key_path.exists():
            content = key_path.read_text().strip()
            if content:
                logger.debug(
                    "llm_key_source=tenant_mount tenant=%s provider=%s",
                    tenant_id,
                    provider,
                )
                return content

        # 2. Env var por tenant (dev)
        env_per_tenant = f"{self.config.env_prefix_per_tenant}{tenant_id}_{provider.upper()}"
        val = os.environ.get(env_per_tenant)
        if val:
            logger.debug(
                "llm_key_source=tenant_env tenant=%s provider=%s",
                tenant_id,
                provider,
            )
            return val

        # 3. Global fallback
        global_var = self.config.env_global_var_by_provider.get(provider)
        if global_var:
            val = os.environ.get(global_var)
            if val:
                logger.debug(
                    "llm_key_source=global_fallback tenant=%s provider=%s",
                    tenant_id,
                    provider,
                )
                return val

        raise SecretNotFoundError(
            f"Ninguna API key disponible para tenant={tenant_id} provider={provider}. "
            f"Configurar {env_per_tenant} o {global_var} o montar {key_path}."
        )

    def has_tenant_specific_key(self, tenant_id: UUID, provider: str = "anthropic") -> bool:
        """True si el tenant tiene key propia (no fallback global)."""
        key_path = Path(self.config.secrets_dir) / str(tenant_id) / f"{provider}.key"
        if key_path.exists() and key_path.read_text().strip():
            return True
        env_var = f"{self.config.env_prefix_per_tenant}{tenant_id}_{provider.upper()}"
        return bool(os.environ.get(env_var))


@lru_cache(maxsize=1)
def get_resolver() -> TenantSecretResolver:
    """Resolver singleton para el servicio."""
    return TenantSecretResolver()
