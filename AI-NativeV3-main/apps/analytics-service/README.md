# analytics-service

Agregados analíticos, dashboards, exportación de reportes

**Puerto**: 8005
**Features**: db, events, graphql

## Desarrollo local

```bash
# Desde la raíz del monorepo
cd apps/analytics-service
uv run uvicorn analytics_service.main:app --reload --port 8005

# Chequear que responde
curl http://localhost:8005/health
```

## Tests

```bash
uv run pytest
```

## Estructura

```
analytics-service/
├── src/analytics_service/
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
