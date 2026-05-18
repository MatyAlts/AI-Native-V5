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

## Próximas fases

Esta es la versión F0 (esqueleto). La lógica se desarrolla en fases siguientes
según [docs/plan-detallado-fases.md](../../docs/plan-detallado-fases.md).
