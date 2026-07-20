# api-gateway

API Gateway con autenticación JWT y ruteo a servicios internos

**Puerto**: 8000
**Features**: auth, proxy

## Desarrollo local

```bash
# Desde la raíz del monorepo
cd apps/api-gateway
uv run uvicorn api_gateway.main:app --reload --port 8000

# Chequear que responde
curl http://localhost:8000/health
```

## Tests

```bash
uv run pytest
```

## Estructura

```
api-gateway/
├── src/api_gateway/
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
