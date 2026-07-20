"""Cliente HTTP del classifier-service hacia el ai-gateway.

`AIGatewayClient.complete` es el patrón sync (no streaming) ya usado por
academic-service para el generador de TPs con IA. Se replica acá para el juez
LLM del eje fino (`regimen_llm.py`). El BYOK, el provider y la medición de
costo los resuelve el ai-gateway; este cliente solo arma la llamada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CompleteResult:
    content: str
    model: str
    provider: str
    feature: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool


class AIGatewayClient:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(
        self,
        messages: list[dict],
        model: str,
        feature: str,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> CompleteResult:
        """POST /api/v1/complete (sync). `materia_id` propaga el scope BYOK."""
        headers = {
            "X-Tenant-Id": str(tenant_id),
            "X-Caller": "classifier-service",
            "Content-Type": "application/json",
        }
        body: dict = {
            "messages": messages,
            "model": model,
            "feature": feature,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if materia_id is not None:
            body["materia_id"] = str(materia_id)
        if response_format is not None:
            body["response_format"] = response_format

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/v1/complete",
                json=body,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        return CompleteResult(
            content=data["content"],
            model=data["model"],
            provider=data.get("provider", "unknown"),
            feature=data.get("feature", feature),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            cache_hit=bool(data.get("cache_hit", False)),
        )
