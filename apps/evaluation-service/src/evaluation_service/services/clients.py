"""Clientes HTTP del evaluation-service hacia los servicios internos.

Dos, y los dos existen por el mismo invariante del proyecto: **ningún servicio
llama a un proveedor de LLM directo, y ningún prompt vive como string en el
código.** El primero pasa por el `ai-gateway` (que resuelve BYOK, presupuesto y
costo); el segundo se pide al `governance-service`, que lo sirve con su hash.

Ese hash no es decorativo. Una nota es una decisión sobre una persona, y
«¿por qué le puso 6?» tres meses después sólo tiene respuesta si quedó
registrado con qué texto exacto se corrigió.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx


class AIGatewayError(RuntimeError):
    """El gateway no devolvió una respuesta usable. Es infraestructura."""


class PromptNoDisponibleError(RuntimeError):
    """No se pudo traer el prompt versionado. Es infraestructura."""


@dataclass(frozen=True)
class CompleteResult:
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class PromptConfig:
    name: str
    version: str
    content: str
    hash: str


class AIGatewayClient:
    """`POST /api/v1/complete`, sincrónico. Mismo contrato que usa el classifier."""

    def __init__(self, base_url: str, timeout: float = 90.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(
        self,
        *,
        messages: list[dict],
        model: str,
        feature: str,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> CompleteResult:
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

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/v1/complete",
                    json=body,
                    headers={
                        "X-Tenant-Id": str(tenant_id),
                        "X-Caller": "evaluation-service",
                        "Content-Type": "application/json",
                    },
                )
        except (httpx.HTTPError, OSError) as e:
            raise AIGatewayError(f"El ai-gateway no respondió: {type(e).__name__}") from e

        if r.status_code >= 400:
            # El cuerpo del gateway nombra la causa real —presupuesto agotado,
            # key sin cupo, proveedor caído— y sin él el docente ve un número.
            detalle = r.text[:300]
            raise AIGatewayError(f"El ai-gateway respondió {r.status_code}. {detalle}".strip())

        data = r.json()
        contenido = data.get("content")
        if not contenido:
            raise AIGatewayError("El ai-gateway respondió sin contenido.")
        return CompleteResult(
            content=contenido,
            model=data.get("model") or model,
            provider=data.get("provider") or "unknown",
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
        )


class GovernanceClient:
    """`GET /api/v1/prompts/{name}/{version}` — el texto y su SHA-256."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.base_url}/api/v1/prompts/{name}/{version}")
        except (httpx.HTTPError, OSError) as e:
            raise PromptNoDisponibleError(
                f"El governance-service no respondió: {type(e).__name__}"
            ) from e

        if r.status_code == 404:
            raise PromptNoDisponibleError(
                f"El prompt {name}/{version} no está publicado en el governance-service."
            )
        if r.status_code >= 400:
            raise PromptNoDisponibleError(f"El governance-service respondió {r.status_code}.")

        data = r.json()
        return PromptConfig(
            name=data["name"],
            version=data["version"],
            content=data["content"],
            hash=data["hash"],
        )
