"""execution-service: ejecucion server-side de codigo de alumnos (ADR-059).

Intermediario entre el alumno y el sandbox. Existe como servicio propio y no
como endpoint del tutor-service por tres razones (D1 del design):

  - **Radio de impacto**: el sandbox exige contenedor privilegiado. Si la logica
    que le habla viviera dentro del tutor —que maneja el flujo conversacional,
    las sesiones de todos los episodios activos y el streaming— un compromiso de
    ese proceso quedaria en el mismo radio que el componente que dialoga con un
    sandbox privilegiado.
  - **Despliegue diferenciado**: el sandbox vive fuera del VPS de produccion
    (ADR-059 D2), asi que el servicio que le habla es operacionalmente otro
    despliegue.
  - **Regla operativa existente**: redesplegar el tutor-service con alumnos
    activos desincroniza el `next_seq` del CTR y rompe episodios sin
    recuperacion. Sumarle motivos de redespliegue —ajustar cuotas, cambiar la
    direccion del sandbox— empeora un problema conocido.

Cuatro responsabilidades que el sandbox por si solo no cubre: inyectar los casos
ocultos sin mandarlos al navegador, aplicar cuotas por alumno, traducir el
resultado al formato de casos del sistema, y emitir el evento de trazabilidad.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from execution_service.config import settings
from execution_service.observability import setup_observability
from execution_service.routes import executions, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)

    # Sin `INTERNAL_SERVICE_TOKEN` compartido con el tutor-service, los
    # ejercicios CON casos ocultos pierden su `tests_ejecutados`: el tutor los
    # rechaza con 422 (solo un emisor interno verificado puede reportar ocultos)
    # y este servicio falla soft. El resto sigue andando, asi que el sintoma es
    # un agujero en el corpus, no una caida — y aparece justo en los ejercicios
    # que sostienen el claim del ADR-060.
    #
    # No se aborta el arranque a proposito: ejecutar codigo es la funcion
    # principal y sigue siendo correcta sin esto. Pero tiene que gritar al
    # arrancar, no descubrirse contando episodios tres meses despues.
    if not settings.internal_service_token:
        logging.getLogger(__name__).error(
            "INTERNAL_SERVICE_TOKEN vacio — los ejercicios con casos OCULTOS no van a "
            "registrar `tests_ejecutados` en el CTR (el tutor-service los rechaza con "
            "422 y la emision falla soft). Tiene que ser el MISMO valor que el del "
            "tutor-service. Vigilar `execution_ctr_emissions_failed_total`."
        )

    yield


app = FastAPI(
    title="execution-service",
    description="Ejecucion server-side de codigo de alumnos en sandbox aislado (ADR-059)",
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
app.include_router(executions.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "execution-service", "version": "0.1.0", "status": "operational"}
