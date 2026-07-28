"""Schemas de request/response del content-service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── Material ──────────────────────────────────────────────────────────


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    # Migration 20260606_0001 hizo comision_id nullable y agregó materia_id.
    # Ambos pueden coexistir hasta el drop futuro de comision_id.
    comision_id: UUID | None = None
    materia_id: UUID | None = None
    tipo: str
    nombre: str
    tamano_bytes: int
    estado: str
    uploaded_by: UUID
    created_at: datetime
    indexed_at: datetime | None = None
    error_message: str | None = None
    chunks_count: int
    meta: dict[str, Any]


class MaterialListOut(BaseModel):
    data: list[MaterialOut]
    meta: dict[str, Any] = Field(default_factory=dict)


# ── Chunk ─────────────────────────────────────────────────────────────


class ChunkOut(BaseModel):
    """Versión expuesta de un chunk, sin el embedding crudo (1024 floats,
    irrelevante para UI). Sí expone `embedding_model` + `has_embedding` para que
    el docente vea con qué se indexó y si el vector realmente existe (F3 —
    observabilidad del RAG, relacionado con BUG-4)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    # Migration 20260606_0001 hizo comision_id nullable y agregó materia_id.
    comision_id: UUID | None = None
    materia_id: UUID | None = None
    contenido: str
    chunk_type: str
    position: int
    meta: dict[str, Any]
    embedding_model: str | None = None
    has_embedding: bool = False


class MaterialChunksOut(BaseModel):
    """Chunks de un material + metadata del modo de embedding con el que se
    indexó. `is_semantic_embedding` es False cuando el corpus se indexó con el
    embedder mock (vectores por hash, retrieval NO real — BUG-4)."""

    material_id: UUID
    estado: str
    chunks_count: int
    embedding_model: str | None = None
    is_semantic_embedding: bool | None = None
    data: list[ChunkOut]
    meta: dict[str, Any] = Field(default_factory=dict)


# ── Retrieval ─────────────────────────────────────────────────────────


class RetrievalRequest(BaseModel):
    """Input de un retrieval de RAG.

    `materia_id` es el filtro principal de aislamiento. `comision_id` se
    mantiene como alias deprecated para backwards-compat de callers
    que aun no migraron.

    Al menos uno de los dos DEBE estar presente. Si ambos estan, se usa
    `materia_id`.
    """

    query: str = Field(min_length=1, max_length=2000)
    materia_id: UUID | None = None
    comision_id: UUID | None = None  # Deprecated: usar materia_id
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def at_least_one_scope(self) -> RetrievalRequest:
        if self.materia_id is None and self.comision_id is None:
            msg = "At least one of materia_id or comision_id must be provided"
            raise ValueError(msg)
        return self


class RetrievedChunk(BaseModel):
    """Chunk devuelto con su score de similitud y scoring del re-ranker."""

    id: UUID
    contenido: str
    material_id: UUID
    material_nombre: str
    position: int
    chunk_type: str
    meta: dict[str, Any]
    score_vector: float  # 0 a 1 (1 - cosine distance)
    score_rerank: float | None = None  # del cross-encoder si corrió


class RetrievalResponse(BaseModel):
    """Resultado del retrieval + hash para auditoría en el CTR."""

    chunks: list[RetrievedChunk]
    chunks_used_hash: str  # sha256 de los IDs de chunks devueltos, para CTR
    latency_ms: float
    rerank_applied: bool
    # Modo del pipeline, para que el CALLER pueda distinguir un retrieval real
    # de uno con vectores mock (hash). `RetrievalTestResponse` ya lo exponía,
    # pero solo al endpoint de prueba del docente: los consumidores reales
    # (tutor, generador de ejercicios) lo recibían y no tenían forma de saber
    # si los chunks eran relevantes o ruido determinista.
    # Default `True` para no romper callers viejos que construyen la respuesta
    # sin el campo; el service siempre lo setea explícito.
    is_semantic_embedding: bool = True
    embedder_model: str = ""


# ── Ingestion ─────────────────────────────────────────────────────────


class IngestionStatus(BaseModel):
    """Estado de una ingesta en curso para feedback al frontend."""

    material_id: UUID
    estado: Literal["uploaded", "extracting", "chunking", "embedding", "indexed", "failed"]
    progress_pct: int = Field(ge=0, le=100)
    chunks_created: int = 0
    error_message: str | None = None


# ── Retrieval test (F3: "probá una consulta" desde la UI del docente) ──


class RetrievalTestRequest(BaseModel):
    """Input del probador de retrieval del docente. Scope siempre por materia
    (la UI del docente resuelve el materia_id de la comisión activa)."""

    query: str = Field(min_length=1, max_length=2000)
    materia_id: UUID
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class RetrievalTestResponse(BaseModel):
    """Resultado del retrieval real (embed query + búsqueda vectorial + rerank)
    más el modo del pipeline, para que el docente sepa si los scores son reales.

    `is_semantic_embedding=False` ⇒ el índice usa vectores mock (hash): los
    scores NO reflejan relevancia semántica real (BUG-4 / F3(d))."""

    chunks: list[RetrievedChunk]
    chunks_used_hash: str
    latency_ms: float
    rerank_applied: bool
    embedder_model: str
    is_semantic_embedding: bool
    reranker_model: str
