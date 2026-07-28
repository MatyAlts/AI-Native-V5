"""Clientes HTTP del academic-service para servicios externos.

Sec 11 epic ai-native-completion: usados por el endpoint TP-gen IA
(`POST /api/v1/tareas-practicas/generate`).

- `GovernanceClient`: lee el prompt activo del repositorio versionado
  (mismo patron que tutor-service — ai-native-prompts en disco resuelto
  via governance-service).
- `AIGatewayClient`: pega `/api/v1/complete` (sync, no streaming) con
  `feature="tp_generator"` y `materia_id` opcional.

Ambos clientes son sincronos por turno (no streaming): el TP-gen genera
un borrador completo en una invocacion, no necesita SSE como el tutor.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


_generation_semaphore: asyncio.Semaphore | None = None


def get_generation_semaphore() -> asyncio.Semaphore:
    """Semáforo compartido que limita las generaciones IA concurrentes (P-9).

    Ambos endpoints `/generate` (TP y ejercicio) lo adquieren alrededor de la
    llamada al LLM. Se construye perezosamente (dentro del event loop) para no
    fijar un loop al importar el módulo. El límite sale de
    `settings.ai_generation_max_concurrency`.
    """
    global _generation_semaphore
    if _generation_semaphore is None:
        from academic_service.config import settings

        _generation_semaphore = asyncio.Semaphore(settings.ai_generation_max_concurrency)
    return _generation_semaphore


@dataclass
class PromptConfig:
    name: str
    version: str
    content: str
    hash: str


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


@dataclass
class RetrievedChunk:
    contenido: str
    material_nombre: str
    score: float


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    chunks_used_hash: str
    # Modo del pipeline RAG. `is_semantic_embedding=False` ⇒ el índice usa
    # vectores mock (hash SHA-512): el ranking NO refleja relevancia semántica,
    # asi que el top-k es ruido determinista y devuelve los MISMOS chunks para
    # cualquier query. Sin esto en el log era imposible distinguir "el RAG no
    # discrimina" de "hay poco material" (incidente 2026-07-27: dos prompts
    # distintos generaban el mismo ejercicio, con `chunks_used_hash` identico).
    # Default `True` = comportamiento previo si el content-service es viejo.
    is_semantic_embedding: bool = True
    embedder_model: str = ""


class ContentClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def retrieve(
        self,
        query: str,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        comision_id: UUID | None = None,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Retrieve chunks del RAG. Prefiere materia_id; comision_id como fallback."""
        headers = {
            "X-Tenant-Id": str(tenant_id),
            "X-User-Id": "00000000-0000-0000-0000-000000000000",
            "X-User-Email": "academic-service@internal",
            "X-User-Roles": "docente",
            "X-Caller": "academic-service",
        }
        payload: dict[str, object] = {
            "query": query,
            "top_k": top_k,
            "score_threshold": 0.3,
        }
        if materia_id is not None:
            payload["materia_id"] = str(materia_id)
        elif comision_id is not None:
            payload["comision_id"] = str(comision_id)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/v1/retrieve",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        chunks = [
            RetrievedChunk(
                contenido=c["contenido"],
                material_nombre=c.get("material_nombre", ""),
                score=float(c.get("score_vector", 0)),
            )
            for c in data.get("chunks", [])
        ]
        return RetrievalResult(
            chunks=chunks,
            chunks_used_hash=data.get("chunks_used_hash", ""),
            is_semantic_embedding=bool(data.get("is_semantic_embedding", True)),
            embedder_model=str(data.get("embedder_model", "")),
        )


class GovernanceClient:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/api/v1/prompts/{name}/{version}")
            r.raise_for_status()
            data = r.json()
        return PromptConfig(
            name=data.get("name", name),
            version=data.get("version", version),
            content=data["content"],
            hash=data.get("hash", ""),
        )


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
        response_format: dict[str, str] | None = None,
    ) -> CompleteResult:
        """POST /api/v1/complete (sync, sin streaming).

        ADR-040 (Sec 6 epic): `materia_id` se propaga al ai-gateway para que
        el resolver BYOK pueda elegir key con scope=materia primero, con
        fallback a facultad / tenant / env. Si materia_id es None, fallback
        directo a tenant scope.
        """
        headers = {
            "X-Tenant-Id": str(tenant_id),
            "X-Caller": "academic-service",
            "Content-Type": "application/json",
        }
        # Procedencia server-to-server (academic → ai-gateway directo, sin
        # pasar por el api-gateway). Solo si el token está seteado; vacío =>
        # no se manda (backward-compat).
        from academic_service.config import settings

        if settings.internal_service_token:
            headers["X-Internal-Service-Token"] = settings.internal_service_token
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
