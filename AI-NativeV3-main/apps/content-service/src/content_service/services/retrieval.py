"""Retrieval RAG con filtro estricto por materia + re-ranking.

PROPIEDAD CRÍTICA: toda query DEBE incluir `materia_id` (o `comision_id`
como fallback deprecated). El filtro se aplica en dos capas (defensa en
profundidad):

1. RLS por `tenant_id` automático via `current_setting('app.current_tenant')`.
2. WHERE explícito `materia_id = :m` en la query SQL.

El aislamiento es por materia: todas las comisiones de la misma materia
comparten el corpus RAG. Esto es correcto porque el material de
referencia pertenece a la materia, no a una comisión particular.
"""

from __future__ import annotations

import hashlib
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.embedding import get_embedder, get_reranker
from content_service.schemas import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
)

# Cuántos candidatos traer del vector search antes de re-rankear
VECTOR_TOP_N = 20


class RetrievalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        start = time.perf_counter()

        # Resolver scope: materia_id preferido, comision_id como fallback
        scope_id = request.materia_id or request.comision_id
        if scope_id is None:
            return RetrievalResponse(
                chunks=[],
                chunks_used_hash=_hash_chunk_ids([]),
                latency_ms=0.0,
                rerank_applied=False,
            )

        use_materia = request.materia_id is not None
        scope_column = "c.materia_id" if use_materia else "c.comision_id"

        # 1. Embed de la query
        embedder = get_embedder()
        q_vec = await embedder.embed_query(request.query)

        # 2. Top-N por similitud vectorial. Filtro doble:
        #    - RLS implícito (current_setting + tenant_isolation policy)
        #    - materia_id (o comision_id fallback) explícito en WHERE
        rows = await self.session.execute(
            text(f"""
                SELECT
                    c.id,
                    c.contenido,
                    c.material_id,
                    m.nombre AS material_nombre,
                    c.position,
                    c.chunk_type,
                    c.meta,
                    1 - (c.embedding <=> CAST(:q AS vector)) AS score_vector
                FROM chunks c
                JOIN materiales m ON m.id = c.material_id
                WHERE {scope_column} = :scope_id
                  AND c.embedding IS NOT NULL
                  AND m.deleted_at IS NULL
                ORDER BY c.embedding <=> CAST(:q AS vector)
                LIMIT :limit
            """),
            {
                "q": str(q_vec),
                "scope_id": scope_id,
                "limit": VECTOR_TOP_N,
            },
        )

        candidates = rows.mappings().all()

        # Sin resultados: respuesta vacía pero coherente
        if not candidates:
            return RetrievalResponse(
                chunks=[],
                chunks_used_hash=_hash_chunk_ids([]),
                latency_ms=(time.perf_counter() - start) * 1000,
                rerank_applied=False,
            )

        # Filtrar por threshold de similitud vectorial (descartar basura obvia)
        above_threshold = [r for r in candidates if r["score_vector"] >= request.score_threshold]
        if not above_threshold:
            return RetrievalResponse(
                chunks=[],
                chunks_used_hash=_hash_chunk_ids([]),
                latency_ms=(time.perf_counter() - start) * 1000,
                rerank_applied=False,
            )

        # 3. Re-ranking cross-encoder
        reranker = get_reranker()
        texts_to_rerank = [r["contenido"] for r in above_threshold]
        rerank_scores = await reranker.rerank(request.query, texts_to_rerank)

        # 4. Combinar + ordenar por rerank score + top-k
        enriched = [
            {**dict(r), "score_rerank": rs}
            for r, rs in zip(above_threshold, rerank_scores, strict=True)
        ]
        enriched.sort(key=lambda x: x["score_rerank"], reverse=True)
        final = enriched[: request.top_k]

        chunks = [
            RetrievedChunk(
                id=r["id"],
                contenido=r["contenido"],
                material_id=r["material_id"],
                material_nombre=r["material_nombre"],
                position=r["position"],
                chunk_type=r["chunk_type"],
                meta=r["meta"] or {},
                score_vector=float(r["score_vector"]),
                score_rerank=float(r["score_rerank"]),
            )
            for r in final
        ]

        chunks_used_hash = _hash_chunk_ids([c.id for c in chunks])

        return RetrievalResponse(
            chunks=chunks,
            chunks_used_hash=chunks_used_hash,
            latency_ms=(time.perf_counter() - start) * 1000,
            rerank_applied=not isinstance(reranker.__class__.__name__, str)
            or reranker.model_name != "identity",
        )


def _hash_chunk_ids(ids: list[UUID]) -> str:
    """Hash determinista del conjunto de chunks usados, para auditoría CTR.

    Se ordena antes de hashear para que el hash no dependa del orden
    (importante: el tutor puede reordenar internamente pero el conjunto
    usado es lo que importa para reproducibilidad).
    """
    sorted_ids = sorted(str(i) for i in ids)
    joined = "|".join(sorted_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
