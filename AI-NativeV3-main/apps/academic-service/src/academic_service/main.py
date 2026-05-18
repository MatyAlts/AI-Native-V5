"""academic-service: CRUDs del dominio académico.

En F1 expone los endpoints de Universidades, Carreras, Materias,
Periodos y Comisiones con matriz de permisos Casbin.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from academic_service.config import settings
from academic_service.observability import setup_observability
from academic_service.routes import (
    bulk,
    carreras,
    comisiones,
    ejercicios,
    facultades,
    health,
    instrumentos,
    materias,
    planes,
    tareas_practicas,
    tareas_practicas_templates,
    unidades,
    universidades,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    # DB y event bus se inicializan lazy al primer request (o explícito en F3)
    yield


app = FastAPI(
    title="academic-service",
    description="CRUDs del dominio académico (universidades, carreras, comisiones)",
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

# Routers (orden por jerarquía: universidad → facultad → carrera → plan → materia → periodo → comisión)
app.include_router(health.router)
app.include_router(universidades.router)
app.include_router(facultades.router)
app.include_router(carreras.router)
app.include_router(planes.router)
app.include_router(materias.router)
app.include_router(comisiones.periodos_router)
app.include_router(comisiones.comisiones_router)
app.include_router(tareas_practicas.router)
app.include_router(tareas_practicas_templates.router)
app.include_router(ejercicios.router)
app.include_router(unidades.router)
app.include_router(bulk.router)

# Instrumentos del diseno cuasi-experimental (P2-1, P2-2, P2-3 del PlanMejora.md)
app.include_router(instrumentos.cuestionario_ia_router)
app.include_router(instrumentos.pretest_router)
app.include_router(instrumentos.transferencia_router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return JSONResponse(
            status_code=409, content={"detail": "Ya existe un registro con esos datos únicos"}
        )
    return JSONResponse(status_code=409, content={"detail": "Conflicto de integridad de datos"})


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "academic-service",
        "version": "0.1.0",
        "status": "operational",
    }
