"""Servicio evaluation-service: Rúbricas, corrección asistida, calificaciones finales.

Activado en epic tp-entregas-correccion: entregas de alumnos + corrección docente.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from evaluation_service.config import settings
from evaluation_service.observability import setup_observability
from evaluation_service.routes import activeia, correccion_ia, entregas, health
from evaluation_service.services.correccion_worker import (
    reconciliar_running,
    run_reconciliador,
    tenants_con_running,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # El simulador de escritura de rúbricas NO puede quedar prendido en prod.
    # Prendido, `sincronizar_tp` marca los ejercicios como sincronizados
    # contra rúbricas que no existen del otro lado — y después una corrección
    # real usaría un `rubrica_id` inventado. El fallo sería silencioso: la UI
    # diría "sincronizado" y el docente no tendría cómo saberlo.
    #
    # Se cae al arrancar y no se auto-corrige: apagarlo solo dejaría el flag
    # prendido en el env, y el próximo deploy lo repetiría.
    if settings.activeia_mock_escritura and settings.environment == "production":
        raise RuntimeError(
            "ACTIVEIA_MOCK_ESCRITURA está prendido con ENVIRONMENT=production. "
            "Es un simulador: marca rúbricas como sincronizadas sin haberlas "
            "enviado. Apagalo o cambiá el environment."
        )
    setup_observability(app)

    # Reconciliador (tarea 3.16). Un deploy a mitad de una corrección deja
    # filas en `running` para siempre: la UI las mostraría girando y el docente
    # esperaría un resultado que no va a llegar. Se cierran como error de
    # infraestructura y SIN nota — el proceso se murió, que no dice nada sobre
    # el código del alumno.
    #
    # Best-effort: un fallo acá NO impide que el servicio arranque. Dejar el
    # servicio caído por no poder limpiar filas viejas sería peor que las filas
    # viejas.
    reconciliador: asyncio.Task[None] | None = None
    if settings.activeia_enabled:
        try:
            for tenant_id in await tenants_con_running():
                await reconciliar_running(tenant_id)
        except Exception:
            structlog.get_logger().exception("activeia_reconciliador_fallo")

        # Y periódico, no sólo al arrancar: el umbral de "huérfana" son 6
        # minutos, así que un reinicio más rápido que eso dejaba colgadas las
        # correcciones de esa ventana para siempre (auditoría del 19/08).
        reconciliador = asyncio.create_task(
            run_reconciliador(intervalo_s=settings.activeia_reconciliador_intervalo_s)
        )

    try:
        yield
    finally:
        if reconciliador is not None:
            reconciliador.cancel()
            with suppress(asyncio.CancelledError):
                await reconciliador


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
app.include_router(activeia.router)
app.include_router(correccion_ia.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 SIN el campo `input` de pydantic.

    Pydantic v2 incluye en cada error el valor que lo causó. Para un error a
    nivel modelo ese valor es **el body entero**; para uno sobre un campo, el
    campo. En `POST /activeia/credenciales` eso devolvía la contraseña del
    docente en claro dentro del 422 — y no alcanzaba con apagar el kill
    switch, porque la validación del body corre ANTES del cuerpo del endpoint.

    De ahí que el filtro viva acá y no en la ruta: el único lugar que corre
    antes que la ruta es el handler. Y se aplica a TODO el servicio, no sólo a
    ese endpoint: el próximo campo sensible que alguien agregue queda cubierto
    sin que se acuerde de este comentario.

    Se conservan `type`, `loc` y `msg`, que es lo que necesita el cliente para
    saber qué campo está mal. Lo que se pierde es el eco del valor.
    """
    seguros = [
        {"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": seguros})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
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
