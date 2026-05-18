"""Cliente HTTP del content-service para retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    id: UUID
    contenido: str
    material_id: UUID
    material_nombre: str
    position: int
    chunk_type: str
    score_rerank: float | None
    score_vector: float
    meta: dict[str, Any]


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    chunks_used_hash: str
    latency_ms: float
    rerank_applied: bool


class ContentClient:
    """Cliente del content-service.

    Propaga headers `X-*` del tutor-service como service-account para que
    el content-service autorice la llamada (rol `tutor_service`).
    """

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def retrieve(
        self,
        query: str,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        comision_id: UUID | None = None,
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> RetrievalResult:
        """Retrieve chunks del RAG. Prefiere materia_id; comision_id como fallback.

        Guards defensivos para evitar 422 del content-service:
        - Si `query` queda vacío (eg. trim), devolvemos resultado vacío
          sin pegar al endpoint (el schema exige min_length=1).
        - Si no hay materia_id ni comision_id, idem (el schema exige al
          menos uno via `at_least_one_scope` validator).
        El tutor continua el flujo sin RAG cuando esto pasa.
        """
        if not query or not query.strip():
            logger.debug(
                "retrieve skipped: query vacio (tenant=%s)", tenant_id
            )
            return RetrievalResult(
                chunks=[],
                chunks_used_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                latency_ms=0.0,
                rerank_applied=False,
            )
        if materia_id is None and comision_id is None:
            logger.warning(
                "retrieve skipped: ni materia_id ni comision_id (tenant=%s); "
                "RAG sin scope no puede ejecutar — tutor sigue sin contexto",
                tenant_id,
            )
            return RetrievalResult(
                chunks=[],
                chunks_used_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                latency_ms=0.0,
                rerank_applied=False,
            )

        payload: dict[str, object] = {
            "query": query,
            "top_k": top_k,
            "score_threshold": score_threshold,
        }
        if materia_id is not None:
            payload["materia_id"] = str(materia_id)
        elif comision_id is not None:
            payload["comision_id"] = str(comision_id)
        headers = {
            "Content-Type": "application/json",
            "X-User-Id": "00000000-0000-0000-0000-000000000099",  # service-account
            "X-Tenant-Id": str(tenant_id),
            "X-User-Email": "tutor-service@platform.internal",
            "X-User-Roles": "tutor_service",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/retrieve",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        chunks = [
            RetrievedChunk(
                id=UUID(c["id"]),
                contenido=c["contenido"],
                material_id=UUID(c["material_id"]),
                material_nombre=c["material_nombre"],
                position=c["position"],
                chunk_type=c["chunk_type"],
                score_rerank=c.get("score_rerank"),
                score_vector=c["score_vector"],
                meta=c.get("meta") or {},
            )
            for c in data["chunks"]
        ]

        return RetrievalResult(
            chunks=chunks,
            chunks_used_hash=data["chunks_used_hash"],
            latency_ms=data["latency_ms"],
            rerank_applied=data.get("rerank_applied", False),
        )
