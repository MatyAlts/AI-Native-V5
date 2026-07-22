# ADR-011 — pgvector para RAG en MVP

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: rag, ai, datos

## Contexto y problema

El tutor socrático necesita Retrieval Augmented Generation para anclar sus respuestas al material del curso. Se necesita:

- Almacenar embeddings de ~10k-100k chunks por universidad.
- Queries con filtro por `comision_id` (aislamiento estricto) + similarity search.
- Latencia P95 <200ms para el retrieval (top-20 + rerank a top-5).
- Bajo costo operacional en pilotaje.

## Opciones consideradas

### Opción A — pgvector (extensión Postgres)
Extensión nativa que agrega tipo `vector` y operadores de similitud (`<=>`, `<->`, `<#>`). IVFFlat y HNSW como índices aproximados.

### Opción B — Qdrant
Vector DB dedicado. Mejor performance a escala. Operación adicional.

### Opción C — Weaviate
Full-text + vector híbrido nativo. Más pesado operacionalmente.

### Opción D — Pinecone (managed)
Hosted, caro, data sale del país.

### Opción E — FAISS en memoria
Liviano pero sin persistencia estructurada ni filtros.

## Decisión

**Opción A — pgvector en el cluster PostgreSQL existente.**

Detalles:

- Tipo `vector(1024)` para `multilingual-e5-large`.
- Índice IVFFlat con `lists=100` (suficiente para <10M chunks).
- Índice compuesto `(tenant_id, comision_id)` para el filtro previo al vector search.
- Consulta típica:

```sql
SELECT id, contenido, 1 - (embedding <=> :q) AS score
FROM chunks
WHERE tenant_id = current_setting('app.current_tenant')::uuid
  AND comision_id = :comision_id
ORDER BY embedding <=> :q
LIMIT 20;
```

Re-ranker `bge-reranker-base` local reordena los 20 candidatos y devuelve top-5.

Migración a Qdrant planificada **solo si** se superan los ~10M chunks con latencia degradada.

## Consecuencias

### Positivas
- Una sola base para operar: RLS aplica también a chunks.
- Sin servicios adicionales en pilotaje.
- Embeddings + metadata en la misma transacción que ingesta de materiales.
- Migración a Qdrant es portable: embeddings son arrays de floats.

### Negativas
- IVFFlat tiene ~95% recall (HNSW tiene ~99% pero más costoso). Aceptable con re-ranker posterior.
- A volúmenes >100M chunks, PostgreSQL empieza a sufrir.
- Reindex de IVFFlat al crecer significativamente la data (costoso).

### Neutras
- Si se cambia el modelo de embeddings, todos los chunks requieren re-embed. Mitigamos con columna `embedding_model_version` y re-embedding lazy por uso.

## Referencias

- [pgvector](https://github.com/pgvector/pgvector)
- `apps/content-service/`
- `docs/plan-detallado-fases.md` → F2
