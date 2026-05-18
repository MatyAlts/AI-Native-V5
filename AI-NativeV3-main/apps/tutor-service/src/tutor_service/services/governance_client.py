"""Cliente HTTP del governance-service.

El tutor consulta al governance para obtener el prompt system activo +
su hash. El hash se incluye en cada evento CTR emitido durante el
episodio, lo cual permite auditabilidad y reproducibilidad (ADR-009).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ActivePrompt:
    name: str
    version: str
    content: str
    hash: str


class GovernanceClient:
    """Cliente async del governance-service."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def active_configs(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/api/v1/active_configs")
            resp.raise_for_status()
            return resp.json()

    async def load_prompt(self, name: str, version: str) -> ActivePrompt:
        """Carga un prompt verificado."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/api/v1/prompts/{name}/{version}")
            resp.raise_for_status()
            data = resp.json()
            return ActivePrompt(
                name=data["name"],
                version=data["version"],
                content=data["content"],
                hash=data["hash"],
            )

    async def resolve_for_tenant(self, tenant_id: str, prompt_name: str = "tutor") -> ActivePrompt:
        """Obtiene el prompt activo para un tenant específico.

        Busca primero override por tenant_id en el manifest; si no existe,
        usa el default.
        """
        # Deferred: ADR-024 / piloto-2 — `prompt_kind` reflexivo en runtime
        # introduciría sesgo mid-cohort si se rota durante el piloto.
        # Hoy se usa el prompt activo del manifest sin clasificación dinámica.
        configs = await self.active_configs()
        active = configs.get("active", {})
        version = active.get(tenant_id, {}).get(prompt_name) or active.get("default", {}).get(
            prompt_name
        )
        if not version:
            raise RuntimeError(
                f"No hay versión activa para prompt={prompt_name} tenant={tenant_id}"
            )
        return await self.load_prompt(prompt_name, version)
