# ctr-service

Cognitive Trace Record: cadena SHA-256 append-only

**Puerto**: 8007
**Features**: db, alembic, events, worker

## Desarrollo local

```bash
# Desde la raíz del monorepo
cd apps/ctr-service
uv run uvicorn ctr_service.main:app --reload --port 8007

# Chequear que responde
curl http://localhost:8007/health
```

## Tests

```bash
uv run pytest
```

## Estructura

```
ctr-service/
├── src/ctr_service/
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
