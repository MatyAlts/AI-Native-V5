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

    def __init__(
        self, base_url: str, timeout: float = 10.0, internal_service_token: str = ""
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.internal_service_token = internal_service_token
        self._client = httpx.AsyncClient(timeout=timeout)

    def _service_headers(self) -> dict[str, str]:
        """Header de procedencia service-to-service (A0.1/A0.4).

        Solo se manda si hay token configurado. Token vacio => dict vacio =>
        request identico al comportamiento previo (backward-compat flag-OFF).
        """
        if self.internal_service_token:
            return {"X-Internal-Service-Token": self.internal_service_token}
        return {}

    async def active_configs(self) -> dict[str, Any]:
        client = self._client
        resp = await client.get(
            f"{self.base_url}/api/v1/active_configs",
            headers=self._service_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def load_prompt(self, name: str, version: str) -> ActivePrompt:
        """Carga un prompt verificado."""
        client = self._client
        resp = await client.get(
            f"{self.base_url}/api/v1/prompts/{name}/{version}",
            headers=self._service_headers(),
        )
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
