# governance-service

Custodia del prompt versionado con Git + GPG signing

**Puerto**: 8010
**Features**: core

## Desarrollo local

```bash
# Desde la raíz del monorepo
cd apps/governance-service
uv run uvicorn governance_service.main:app --reload --port 8010

# Chequear que responde
curl http://localhost:8010/health
```

## Tests

```bash
uv run pytest
```

## Estructura

```
governance-service/
├── src/governance_service/
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
