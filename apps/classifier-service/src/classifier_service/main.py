"""classifier-service: clasificación N4 con árbol explicable."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from classifier_service.config import settings
from classifier_service.observability import setup_observability
from classifier_service.routes import classify_ep, health, interrater


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="classifier-service",
    description="Clasificador N4 con árbol de decisión explicable",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(health.config_router)
app.include_router(classify_ep.router)
app.include_router(interrater.router)


# Marcador de build: bump para forzar rebuild/recreación del container en EasyPanel
# e invalidar la caché de Docker. Verificación: tras redeployar, `GET /` debe
# devolver este `build_marker` → confirma que el container nuevo tomó el código nuevo.
BUILD_MARKER = "interrater-corpus-con-tutor-2026-06-24"


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "classifier-service",
        "version": "0.1.0",
        "status": "operational",
        "build_marker": BUILD_MARKER,
    }
