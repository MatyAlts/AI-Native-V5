# content-service

Ingesta multi-formato, chunking, embeddings, retrieval RAG

**Puerto**: 8009
**Features**: db, events, ai

## Desarrollo local

```bash
# Desde la raíz del monorepo
cd apps/content-service
uv run uvicorn content_service.main:app --reload --port 8009

# Chequear que responde
curl http://localhost:8009/health
```

## Tests

```bash
uv run pytest
```

## Estructura

```
content-service/
├── src/content_service/
│   ├── __init__.py
│   ├── main.py           # FastAPI app + lifespan
│   ├── config.py         # Settings Pydantic
│   ├── observability.py  # OpenTelemetry + structlog
│   └── routes/
│       ├── __init__.py
│       └── health.py     # /health endpoints
├── tests/
│   └── test_health.py
├── pyproject.toml
├── Dockerfile
└── README.md
```

## Embedder: mock (dev) vs real (prod)

El pipeline resuelve el embedder en `embedding/embedder.py::get_embedder()`
según la env var `EMBEDDER`:

| `EMBEDDER` | Embedder | Semántico | Uso |
|---|---|---|---|
| `mock` | `MockEmbedder` (hash SHA-512 → 1024 dims) | **No** | dev/tests: retrieval reproducible pero NO real |
| `gemini` | `GeminiEmbedder` (`gemini-embedding-001` via REST) | Sí | **prod recomendado**. Requiere `GEMINI_API_KEY` |
| `local` | `SentenceTransformerEmbedder` (`multilingual-e5-large`) | Sí | prod self-hosted. Requiere `sentence-transformers` + `torch` |
| _(vacío)_ | intenta `local`, cae a `mock` si faltan deps | depende | fallback silencioso — peligroso en prod |

**Guard anti-embeddings-falsos (BUG-4)**: si se resuelve a un embedder
NO-semántico (mock, sea explícito o por fallback) con `ENVIRONMENT`
`production|prod|staging`, `get_embedder()` levanta `RuntimeError` — es imposible
indexar/consultar con vectores falsos creyendo que son reales. En dev el mock es
válido pero queda marcado (`WARNING` + `Chunk.embedding_model="mock-deterministic"`).

**Activar el embedder real en prod (EasyPanel)**: setear en el servicio
`content-service` las env vars `EMBEDDER=gemini` + `GEMINI_API_KEY=<clave>`
(NO commitear la clave). Tras cambiar el embedder, reprocesá los materiales
existentes (`POST /api/v1/materiales/{id}/reingest`) para re-indexarlos con
vectores reales.

## Observabilidad del RAG (F3)

Endpoints read-only para que el docente verifique el corpus desde web-teacher
(vista Materiales). Todos bajo el prefijo `/api/v1/materiales`, ya ruteado por el
api-gateway (no requieren entrada nueva en el `ROUTE_MAP`):

- `GET  /api/v1/materiales/{id}/chunks` — chunks generados (texto, orden,
  metadata, `has_embedding`) + modo de embedding con el que se indexó
  (`embedding_model`, `is_semantic_embedding`).
- `POST /api/v1/materiales/probar-retrieval` — corre el retrieval REAL
  (embed query + búsqueda vectorial + rerank) y devuelve los top-k con
  `score_vector`/`score_rerank` + el modo del pipeline. Read-only, no muta nada.
- `POST /api/v1/materiales/{id}/reingest` — re-procesa el material desde su
  original en storage (útil tras un `failed`, un corpus sin chunks, o al activar
  el embedder real). Idempotente: borra los chunks previos.

## Próximas fases

Esta es la versión F0 (esqueleto). La lógica se desarrolla en fases siguientes
según [docs/plan-detallado-fases.md](../../docs/plan-detallado-fases.md).
