"""Re-indexa los embeddings de chunks ya existentes usando el embedder
configurado en EMBEDDER del environment (local por default).

Uso:
    EMBEDDER=local CONTENT_DB_URL=... uv run python scripts/reindex-content-embeddings.py

Pasos:
    1. Conecta a content_db.
    2. Lee TODOS los chunks (id, contenido) en batches.
    3. Embebe cada batch con el embedder configurado.
    4. UPDATEa la columna embedding del chunk.

Sirve para:
    - Migrar de mock embedder a embedder real (sentence-transformers / openai).
    - Cambiar de modelo de embeddings (ej. de e5-large a e5-base).

NO toca:
    - Los chunks (texto/metadata).
    - Los materiales.
    - Ningun otro schema.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Permitir que el script encuentre los packages workspace
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "content-service" / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BATCH_SIZE = 32


async def main() -> int:
    dsn = os.environ.get(
        "CONTENT_DB_URL",
        "postgresql+asyncpg://content_user:content_pass@localhost:5432/content_db",
    )
    embedder_name = os.environ.get("EMBEDDER", "")

    # Force-import del embedder para verificar que el factory devuelva el que esperamos
    from content_service.embedding import get_embedder

    embedder = get_embedder()
    print(f"Embedder seleccionado: {type(embedder).__name__} (EMBEDDER='{embedder_name}')")
    print(f"  model_name: {getattr(embedder, 'model_name', '?')}")

    engine = create_async_engine(dsn, pool_pre_ping=True)

    async with engine.connect() as conn:
        # Set RLS para poder leer/escribir chunks
        await conn.exec_driver_sql("SET LOCAL app.current_tenant = '00000000-0000-0000-0000-000000000000'")

        # Contar
        count_result = await conn.exec_driver_sql("SELECT count(*) FROM chunks")
        total = count_result.scalar_one()
        print(f"Total chunks a re-indexar: {total}")
        if total == 0:
            print("Nada que hacer.")
            return 0

        # Calentar el modelo con un embed dummy (la primera carga descarga ~2GB
        # de pesos del modelo e5-large desde HuggingFace si no esta cacheado).
        print("Calentando modelo (puede descargar pesos la primera vez)...")
        t0 = time.perf_counter()
        await embedder.embed_query("warmup")
        print(f"  Modelo listo en {time.perf_counter() - t0:.1f}s")

    # Re-engine para que el SET LOCAL no persista
    async with engine.connect() as conn:
        # Bypass RLS: necesitamos leer y escribir todos los tenants
        # (este script es admin/migration, no API path)
        await conn.exec_driver_sql("SET row_security = off")

        # Leer chunks en batches
        offset = 0
        total_done = 0
        t_start = time.perf_counter()

        while True:
            rows = await conn.exec_driver_sql(
                f"SELECT id, contenido FROM chunks ORDER BY created_at LIMIT {BATCH_SIZE} OFFSET {offset}"
            )
            batch = rows.fetchall()
            if not batch:
                break

            chunk_ids = [row[0] for row in batch]
            texts = [row[1] for row in batch]

            t0 = time.perf_counter()
            vectors = await embedder.embed_documents(texts)
            t_embed = time.perf_counter() - t0

            # UPDATE cada chunk con su vector nuevo. Usamos text() porque
            # exec_driver_sql con asyncpg no acepta :name params.
            t0 = time.perf_counter()
            update_stmt = text(
                "UPDATE chunks SET embedding = :vec, embedding_model = :model WHERE id = :id"
            )
            for cid, vec in zip(chunk_ids, vectors, strict=True):
                # pgvector toma el vector como string en formato '[v1,v2,...]'
                vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
                await conn.execute(
                    update_stmt,
                    {"vec": vec_str, "model": embedder.model_name, "id": str(cid)},
                )
            t_update = time.perf_counter() - t0

            total_done += len(batch)
            print(
                f"  batch {offset // BATCH_SIZE + 1}: "
                f"{len(batch)} chunks → embed {t_embed:.2f}s, update {t_update:.2f}s "
                f"(total {total_done}/{total})"
            )
            offset += BATCH_SIZE

        # Commit del transaction
        await conn.commit()

        t_total = time.perf_counter() - t_start
        print(f"\nRe-indexación completada: {total_done} chunks en {t_total:.1f}s")
        print(f"  Throughput: {total_done / t_total:.1f} chunks/s")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
