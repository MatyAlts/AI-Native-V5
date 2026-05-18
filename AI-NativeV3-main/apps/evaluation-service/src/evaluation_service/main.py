"""Servicio evaluation-service: Rúbricas, corrección asistida, calificaciones finales.

Activado en epic tp-entregas-correccion: entregas de alumnos + corrección docente.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from evaluation_service.config import settings
from evaluation_service.observability import setup_observability
from evaluation_service.routes import entregas, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="evaluation-service",
    description="Rúbricas, corrección asistida, calificaciones finales",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router)
app.include_router(entregas.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return JSONResponse(
            status_code=409,
            content={"detail": "Ya existe un registro con esos datos unicos"},
        )
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflicto de integridad de datos"},
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "evaluation-service",
        "version": "0.2.0",
        "status": "operational",
    }
