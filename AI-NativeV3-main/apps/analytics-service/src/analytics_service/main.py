"""Servicio analytics-service: Agregados analíticos, dashboards, exportación de reportes"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics_service.config import settings
from analytics_service.observability import setup_observability
from analytics_service.routes import analytics, export_standards, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup y shutdown del servicio."""
    from analytics_service.services.export import start_worker, stop_worker

    # Startup
    setup_observability(app)
    await start_worker()
    yield
    # Shutdown
    await stop_worker()


app = FastAPI(
    title="analytics-service",
    description="Agregados analíticos, dashboards, exportación de reportes",
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
app.include_router(analytics.router)

# Caliper Analytics 1.2 + xAPI 1.0.3 exporters (P3-1 del PlanMejora.md, paper §5.1)
app.include_router(export_standards.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "analytics-service",
        "version": "0.1.0",
        "status": "operational",
    }
