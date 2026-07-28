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
