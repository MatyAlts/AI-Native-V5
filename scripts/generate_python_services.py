#!/usr/bin/env python3
"""Genera los esqueletos de los 12 servicios Python del monorepo.

Cada servicio tiene:
- pyproject.toml con dependencias base + específicas
- Dockerfile multi-stage con distroless
- src/<service>/main.py con FastAPI + /health
- src/<service>/config.py con settings Pydantic
- src/<service>/observability.py con OpenTelemetry
- tests/ con test_health.py
- README.md específico
"""

from pathlib import Path
from textwrap import dedent

ROOT = Path("/home/claude/platform")
APPS = ROOT / "apps"

# Definición de cada servicio: nombre, descripción, puerto, dependencias extra, features
SERVICES = [
    {
        "name": "api-gateway",
        "module": "api_gateway",
        "description": "API Gateway con autenticación JWT y ruteo a servicios internos",
        "port": 8000,
        "extra_deps": ["httpx>=0.27"],
        "features": ["auth", "proxy"],
    },
    {
        "name": "identity-service",
        "module": "identity_service",
        "description": "Wrapper de la Admin API de Keycloak + gestión de pseudonimización",
        "port": 8001,
        "extra_deps": ["python-keycloak>=4.0"],
        "features": ["auth", "db"],
    },
    {
        "name": "academic-service",
        "module": "academic_service",
        "description": "CRUDs del dominio académico (universidades, carreras, comisiones)",
        "port": 8002,
        "extra_deps": ["alembic>=1.13", "asyncpg>=0.29"],
        "features": ["db", "alembic", "events"],
    },
    {
        "name": "enrollment-service",
        "module": "enrollment_service",
        "description": "Gestión de inscripciones y sincronización con SIS institucionales",
        "port": 8003,
        "extra_deps": ["pandas>=2.2", "httpx>=0.27"],
        "features": ["db", "events"],
    },
    {
        "name": "evaluation-service",
        "module": "evaluation_service",
        "description": "Rúbricas, corrección asistida, calificaciones finales",
        "port": 8004,
        "extra_deps": ["jsonschema>=4.21", "weasyprint>=62"],
        "features": ["db", "events"],
    },
    {
        "name": "analytics-service",
        "module": "analytics_service",
        "description": "Agregados analíticos, dashboards, exportación de reportes",
        "port": 8005,
        "extra_deps": ["strawberry-graphql[fastapi]>=0.235"],
        "features": ["db", "events", "graphql"],
    },
    {
        "name": "tutor-service",
        "module": "tutor_service",
        "description": "Tutor socrático con prompt versionado y streaming SSE",
        "port": 8006,
        "extra_deps": ["sse-starlette>=2.1", "anthropic>=0.40"],
        "features": ["events", "ai"],
    },
    {
        "name": "ctr-service",
        "module": "ctr_service",
        "description": "Cognitive Trace Record: cadena SHA-256 append-only",
        "port": 8007,
        "extra_deps": ["alembic>=1.13", "asyncpg>=0.29"],
        "features": ["db", "alembic", "events", "worker"],
    },
    {
        "name": "classifier-service",
        "module": "classifier_service",
        "description": "Clasificador N4 con tres dimensiones de coherencia",
        "port": 8008,
        "extra_deps": ["scikit-learn>=1.5", "numpy>=1.26", "sentence-transformers>=3.0"],
        "features": ["db", "events", "worker", "ai"],
    },
    {
        "name": "content-service",
        "module": "content_service",
        "description": "Ingesta multi-formato, chunking, embeddings, retrieval RAG",
        "port": 8009,
        "extra_deps": [
            "unstructured[pdf]>=0.14",
            "sentence-transformers>=3.0",
            "tree-sitter>=0.22",
            "pgvector>=0.3",
        ],
        "features": ["db", "events", "ai"],
    },
    {
        "name": "governance-service",
        "module": "governance_service",
        "description": "Custodia del prompt versionado con Git + GPG signing",
        "port": 8010,
        "extra_deps": ["gitpython>=3.1"],
        "features": [],
    },
    {
        "name": "ai-gateway",
        "module": "ai_gateway",
        "description": "Centraliza invocaciones a LLMs con budget + routing + circuit breakers",
        "port": 8011,
        "extra_deps": ["anthropic>=0.40", "openai>=1.40", "tenacity>=8.5"],
        "features": ["ai"],
    },
]


def pyproject_content(svc: dict) -> str:
    extra_deps = "\n".join(f'    "{d}",' for d in svc["extra_deps"])
    return dedent(f'''\
        [project]
        name = "platform-{svc["name"]}"
        version = "0.1.0"
        description = "{svc["description"]}"
        requires-python = ">=3.12,<3.13"

        dependencies = [
            "fastapi>=0.115",
            "uvicorn[standard]>=0.30",
            "pydantic>=2.8",
            "pydantic-settings>=2.4",
            "sqlalchemy>=2.0",
            "redis>=5.0",
            "structlog>=24.4",
            "opentelemetry-api>=1.27",
            "opentelemetry-sdk>=1.27",
            "opentelemetry-instrumentation-fastapi>=0.48b0",
            "opentelemetry-exporter-otlp>=1.27",
            "platform-contracts",
        {extra_deps}
        ]

        [dependency-groups]
        dev = [
            "pytest>=8.3",
            "pytest-asyncio>=0.24",
            "pytest-cov>=5.0",
            "httpx>=0.27",
            "testcontainers[postgres,redis]>=4.8",
            "hypothesis>=6.108",
            "platform-test-utils",
        ]

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["src/{svc["module"]}"]

        [tool.pytest.ini_options]
        asyncio_mode = "auto"
        testpaths = ["tests"]
        pythonpath = ["src"]
    ''')


def dockerfile_content(svc: dict) -> str:
    return dedent(f'''\
        # Build stage: install dependencies with uv
        FROM python:3.12-slim AS builder

        ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
        RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \\
            --mount=type=cache,target=/root/.cache/uv \\
            --mount=type=bind,source=pyproject.toml,target=pyproject.toml \\
            uv sync --no-install-project --no-dev

        COPY . /app
        WORKDIR /app
        RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \\
            --mount=type=cache,target=/root/.cache/uv \\
            uv sync --no-dev

        # Runtime stage: distroless python
        FROM gcr.io/distroless/python3-debian12:nonroot

        COPY --from=builder --chown=nonroot:nonroot /app /app
        WORKDIR /app

        ENV PATH="/app/.venv/bin:$PATH" \\
            PYTHONUNBUFFERED=1 \\
            PYTHONDONTWRITEBYTECODE=1

        EXPOSE {svc["port"]}

        ENTRYPOINT ["/app/.venv/bin/python", "-m", "uvicorn", "{svc["module"]}.main:app", "--host", "0.0.0.0", "--port", "{svc["port"]}"]
    ''')


def main_py_content(svc: dict) -> str:
    module = svc["module"]
    has_events = "events" in svc["features"]
    has_db = "db" in svc["features"]
    has_worker = "worker" in svc["features"]

    imports = [
        "from contextlib import asynccontextmanager",
        "from typing import AsyncIterator",
        "",
        "from fastapi import FastAPI",
        "from fastapi.middleware.cors import CORSMiddleware",
        "",
        f"from {module}.config import settings",
        f"from {module}.observability import setup_observability",
        f"from {module}.routes import health",
    ]

    lifespan_body = [
        '    """Startup y shutdown del servicio."""',
        "    # Startup",
        "    setup_observability(app)",
    ]
    if has_db:
        lifespan_body.append("    # await db.connect()")
    if has_events:
        lifespan_body.append("    # await event_bus.connect()")
    if has_worker:
        lifespan_body.append("    # await start_worker()")
    lifespan_body += [
        "    yield",
        "    # Shutdown",
    ]
    if has_db:
        lifespan_body.append("    # await db.disconnect()")

    return (
        dedent(f'''\
        """Servicio {svc["name"]}: {svc["description"]}"""
        ''')
        + "\n".join(imports)
        + dedent("""


        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """)
        + "\n".join(lifespan_body)
        + dedent(f'''


        app = FastAPI(
            title="{svc["name"]}",
            description="{svc["description"]}",
            version="0.1.0",
            lifespan=lifespan,
        )

        # CORS: configuración abierta en dev, restrictiva en prod (setea en settings)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Routes
        app.include_router(health.router)


        @app.get("/")
        async def root() -> dict[str, str]:
            return {{
                "service": "{svc["name"]}",
                "version": "0.1.0",
                "status": "operational",
            }}
    ''')
    )


def config_py_content(svc: dict) -> str:
    return dedent(f'''\
        """Configuración del servicio {svc["name"]}."""
        from functools import lru_cache

        from pydantic import Field
        from pydantic_settings import BaseSettings, SettingsConfigDict


        class Settings(BaseSettings):
            """Settings leídas de env + .env con validación."""

            model_config = SettingsConfigDict(
                env_file=".env",
                env_file_encoding="utf-8",
                extra="ignore",
            )

            # Service
            service_name: str = "{svc["name"]}"
            service_port: int = {svc["port"]}
            environment: str = Field(default="development")
            log_level: str = Field(default="info")
            log_format: str = Field(default="json")

            # CORS
            cors_origins: list[str] = Field(default_factory=lambda: ["*"])

            # Observability
            otel_endpoint: str = Field(default="http://localhost:4317")
            sentry_dsn: str = Field(default="")

            # Keycloak (la mayoría de servicios valida JWT)
            keycloak_url: str = Field(default="http://localhost:8180")
            keycloak_realm: str = Field(default="demo_uni")


        @lru_cache
        def get_settings() -> Settings:
            return Settings()


        settings = get_settings()
    ''')


def observability_py_content(svc: dict) -> str:
    return dedent(f'''\
        """Setup de OpenTelemetry + structlog para {svc["name"]}."""
        import logging

        import structlog
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from {svc["module"]}.config import settings


        def setup_observability(app: FastAPI) -> None:
            """Configura tracing OTEL + structlog + instrumenta la app FastAPI."""
            # Logging estructurado
            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso", utc=True),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.JSONRenderer()
                    if settings.log_format == "json"
                    else structlog.dev.ConsoleRenderer(),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(
                    logging.getLevelName(settings.log_level.upper())
                ),
                logger_factory=structlog.PrintLoggerFactory(),
                cache_logger_on_first_use=True,
            )

            # Tracing
            resource = Resource.create({{SERVICE_NAME: settings.service_name}})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True))
            )
            trace.set_tracer_provider(provider)

            # Instrumentar FastAPI (auto-captura spans de requests)
            FastAPIInstrumentor.instrument_app(app)
    ''')


def health_py_content(svc: dict) -> str:
    return dedent(f'''\
        """Endpoints de liveness y readiness.

        - /health/live  → siempre 200 si el proceso corre
        - /health/ready → 200 si dependencias están OK (DB, Redis, Keycloak)
        - /health      → alias de readiness por compatibilidad
        """
        from fastapi import APIRouter, status
        from pydantic import BaseModel

        router = APIRouter(prefix="/health", tags=["health"])


        class HealthResponse(BaseModel):
            service: str
            status: str
            version: str
            checks: dict[str, str] = {{}}


        @router.get("", response_model=HealthResponse)
        @router.get("/ready", response_model=HealthResponse)
        async def ready() -> HealthResponse:
            # TODO: chequear dependencias reales (DB ping, Redis ping)
            return HealthResponse(
                service="{svc["name"]}",
                status="ready",
                version="0.1.0",
                checks={{}},
            )


        @router.get("/live", status_code=status.HTTP_200_OK)
        async def live() -> dict[str, str]:
            return {{"status": "alive"}}
    ''')


def routes_init_content() -> str:
    return '"""Rutas HTTP del servicio."""\n'


def module_init_content(svc: dict) -> str:
    return f'"""Servicio {svc["name"]}."""\n__version__ = "0.1.0"\n'


def test_health_content(svc: dict) -> str:
    return dedent(f'''\
        """Tests del endpoint de salud."""
        import pytest
        from httpx import ASGITransport, AsyncClient

        from {svc["module"]}.main import app


        @pytest.fixture
        async def client() -> AsyncClient:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                yield c


        async def test_health_ready(client: AsyncClient) -> None:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "{svc["name"]}"
            assert data["status"] == "ready"


        async def test_health_live(client: AsyncClient) -> None:
            response = await client.get("/health/live")
            assert response.status_code == 200
            assert response.json() == {{"status": "alive"}}


        async def test_root(client: AsyncClient) -> None:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.json()["service"] == "{svc["name"]}"
    ''')


def service_readme_content(svc: dict) -> str:
    features = ", ".join(svc["features"]) or "core"
    return dedent(f"""\
        # {svc["name"]}

        {svc["description"]}

        **Puerto**: {svc["port"]}
        **Features**: {features}

        ## Desarrollo local

        ```bash
        # Desde la raíz del monorepo
        cd apps/{svc["name"]}
        uv run uvicorn {svc["module"]}.main:app --reload --port {svc["port"]}

        # Chequear que responde
        curl http://localhost:{svc["port"]}/health
        ```

        ## Tests

        ```bash
        uv run pytest
        ```

        ## Estructura

        ```
        {svc["name"]}/
        ├── src/{svc["module"]}/
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
    """)


def main() -> None:
    for svc in SERVICES:
        app_dir = APPS / svc["name"]
        src_dir = app_dir / "src" / svc["module"]
        routes_dir = src_dir / "routes"
        tests_dir = app_dir / "tests"

        for d in (src_dir, routes_dir, tests_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Archivos raíz del servicio
        (app_dir / "pyproject.toml").write_text(pyproject_content(svc))
        (app_dir / "Dockerfile").write_text(dockerfile_content(svc))
        (app_dir / "README.md").write_text(service_readme_content(svc))

        # src/module/
        (src_dir / "__init__.py").write_text(module_init_content(svc))
        (src_dir / "main.py").write_text(main_py_content(svc))
        (src_dir / "config.py").write_text(config_py_content(svc))
        (src_dir / "observability.py").write_text(observability_py_content(svc))

        # src/module/routes/
        (routes_dir / "__init__.py").write_text(routes_init_content())
        (routes_dir / "health.py").write_text(health_py_content(svc))

        # tests/
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_health.py").write_text(test_health_content(svc))

        print(f"✓ {svc['name']} generado")

    print(f"\nTotal: {len(SERVICES)} servicios Python creados")


if __name__ == "__main__":
    main()
