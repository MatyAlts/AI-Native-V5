"""Servicio analytics-service: Agregados analíticos, dashboards, exportación de reportes"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics_service.auth import require_gateway_auth
from analytics_service.config import settings
from analytics_service.observability import setup_observability
from analytics_service.routes import analytics, export_standards, health, pedagogia


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
    # Cerrar los engines de DB compartidos (ver analytics_service.db).
    from analytics_service.db import dispose_all

    await dispose_all()


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
# health NO lleva la verificación de firma (A0.1): debe responder a los probes
# de liveness/readiness sin identidad. Los routers de DATOS sí la llevan detrás
# del flag require_gateway_signature (default OFF = no-op). Corre ADEMÁS de la
# validación de headers de cada endpoint (get_tenant_id / get_user_id), no la
# reemplaza.
app.include_router(health.router)

# Cubre kappa, progression, alerts, ab-test-profiles y cohort/export.
app.include_router(analytics.router, dependencies=[Depends(require_gateway_auth)])

# Caliper Analytics 1.2 + xAPI 1.0.3 exporters (P3-1 del PlanMejora.md, paper §5.1)
app.include_router(export_standards.router, dependencies=[Depends(require_gateway_auth)])

# Dashboard pedagógico agregado para el panel admin (sección "Pedagogía")
app.include_router(pedagogia.router, dependencies=[Depends(require_gateway_auth)])


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "analytics-service",
        "version": "0.1.0",
        "status": "operational",
    }
