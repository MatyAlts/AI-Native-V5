"""Pipeline de ingesta: bytes → extracción → chunking → embedding → persistencia.

Esta función orquesta el flujo completo para un Material dado. En F2 es
síncrona (mismo request HTTP); en F3 se mueve a un job async con
Redis Streams para no bloquear uploads grandes.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.embedding import get_embedder
from content_service.extractors import detect_format, get_extractor
from content_service.models import Chunk, Material
from content_service.models.base import utc_now
from content_service.services.chunker import chunk_sections

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    material_id: UUID
    estado: str
    chunks_created: int
    error: str | None = None


class IngestionPipeline:
    """Orquesta extracción + chunking + embedding para un Material."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(
        self,
        material: Material,
        content: bytes,
        filename: str,
    ) -> IngestionResult:
        """Pipeline completo. Actualiza el estado del material."""
        try:
            # 1. Detectar formato
            fmt = detect_format(filename, content)
            if fmt == "unknown":
                raise ValueError(f"Formato no soportado: {filename}")

            material.estado = "extracting"
            await self.session.flush()

            # 2. Extraer
            extractor = get_extractor(fmt)
            extraction = await extractor.extract(content, filename)
            if not extraction.sections:
                raise ValueError("No se pudo extraer contenido útil del archivo")

            material.meta = {
                **(material.meta or {}),
                **extraction.metadata,
            }

            # 3. Chunking
            material.estado = "chunking"
            await self.session.flush()

            chunks = chunk_sections(extraction.sections)
            if not chunks:
                raise ValueError("El chunker no produjo chunks")

            # 4. Embedding (batch)
            material.estado = "embedding"
            await self.session.flush()

            embedder = get_embedder()
            texts = [c.contenido for c in chunks]
            vectors = await embedder.embed_documents(texts)

            # 5. Persistencia: borrar chunks anteriores del material + insertar nuevos
            await self.session.execute(delete(Chunk).where(Chunk.material_id == material.id))

            for final_chunk, vector in zip(chunks, vectors, strict=True):
                chunk_row = Chunk(
                    tenant_id=material.tenant_id,
                    material_id=material.id,
                    materia_id=material.materia_id,
                    comision_id=material.comision_id,
                    contenido=final_chunk.contenido,
                    contenido_hash=final_chunk.contenido_hash,
                    embedding=vector,
                    embedding_model=embedder.model_name,
                    position=final_chunk.position,
                    chunk_type=final_chunk.chunk_type,
                    meta=final_chunk.meta,
                )
                self.session.add(chunk_row)

            material.estado = "indexed"
            material.indexed_at = utc_now().replace(tzinfo=None)
            material.chunks_count = len(chunks)
            material.content_hash = hashlib.sha256(content).hexdigest()
            await self.session.flush()

            return IngestionResult(
                material_id=material.id,
                estado="indexed",
                chunks_created=len(chunks),
            )

        except Exception as e:
            logger.exception("Ingesta falló para material %s", material.id)
            material.estado = "failed"
            material.error_message = str(e)[:500]
            await self.session.flush()
            return IngestionResult(
                material_id=material.id,
                estado="failed",
                chunks_created=0,
                error=str(e),
            )
