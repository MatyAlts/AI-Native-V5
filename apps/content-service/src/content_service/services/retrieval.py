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
import logging
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

logger = logging.getLogger(__name__)

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
                    c.embedding_model,
                    1 - (c.embedding <=> CAST(:q AS vector)) AS score_vector
                FROM chunks c
                JOIN materiales m ON m.id = c.material_id
                WHERE {scope_column} = :scope_id
                  AND c.embedding IS NOT NULL
                  AND m.deleted_at IS NULL
                  AND (c.embedding_model IS NULL OR c.embedding_model = :modelo)
                ORDER BY c.embedding <=> CAST(:q AS vector)
                LIMIT :limit
            """),
            {
                "q": str(q_vec),
                "scope_id": scope_id,
                "limit": VECTOR_TOP_N,
                "modelo": embedder.model_name,
            },
        )

        candidates = rows.mappings().all()

        # Si el filtro dejo afuera chunks de OTRO espacio de embedding, hay que
        # decirlo fuerte: es la unica senal de que el corpus se indexo con un
        # embedder distinto del que consulta.
        await self._avisar_si_hay_corpus_de_otro_embedder(
            scope_column, scope_id, embedder.model_name, encontrados=len(candidates)
        )

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

    async def _avisar_si_hay_corpus_de_otro_embedder(
        self, scope_column: str, scope_id: UUID, modelo: str, *, encontrados: int
    ) -> None:
        """Grita cuando el corpus esta indexado con un embedder distinto.

        POR QUE ESTE CHEQUEO EXISTE (QA 2026-08-31)
        -------------------------------------------
        Cambiar `EMBEDDER` de `local` a `gemini` —o al reves— NO da error.
        Los dos producen vectores de 1024 dims (Gemini rellena con ceros hasta
        llegar), asi que el `<=>` de pgvector compara felizmente dos espacios
        que no tienen nada que ver y devuelve **200 OK con resultados sin
        sentido**: chunks que no hablan del tema, ordenados por una distancia
        que no significa nada.

        Y eso es PEOR que el 500 que estabamos arreglando. El 500 se ve. Un
        retrieval silenciosamente malo se ve como un tutor que responde
        cualquier cosa, y eso se le atribuye al modelo, no a la configuracion.

        El `WHERE` de arriba ya deja afuera los chunks de otro espacio, asi que
        el fallo se convierte en "no hay material" — legible, y honesto. Esto
        de aca es la explicacion de por que no lo hay.

        Los chunks con `embedding_model IS NULL` SI entran: son de antes de que
        existiera la columna, y excluirlos romperia corpus historicos por una
        sospecha que no podemos confirmar.
        """
        fila = (
            await self.session.execute(
                text(f"""
                    SELECT c.embedding_model, COUNT(*) AS n
                    FROM chunks c
                    JOIN materiales m ON m.id = c.material_id
                    WHERE {scope_column} = :scope_id
                      AND c.embedding IS NOT NULL
                      AND m.deleted_at IS NULL
                      AND c.embedding_model IS NOT NULL
                      AND c.embedding_model <> :modelo
                    GROUP BY c.embedding_model
                    ORDER BY n DESC
                    LIMIT 1
                """),
                {"scope_id": scope_id, "modelo": modelo},
            )
        ).first()
        if fila is None:
            return
        logger.error(
            "rag_corpus_de_otro_embedder scope=%s consultando_con=%r "
            "indexado_con=%r chunks_ignorados=%s chunks_usables=%s — "
            "reindexar el material o volver al embedder con el que se indexo",
            scope_id,
            modelo,
            fila[0],
            fila[1],
            encontrados,
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
