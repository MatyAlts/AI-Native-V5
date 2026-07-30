"""Runner: el UNICO componente con acceso al socket de Docker (ADR-060, gate D3).

Se despliega aparte del `execution-service`. Es el que tiene
`/var/run/docker.sock` montado, y por eso es deliberadamente minimo: **un solo
endpoint, sin base de datos, sin Redis, sin clientes HTTP salientes**. Toda su
superficie de ataque entra en una pantalla.

## La propiedad que sostiene

El caller manda **unicamente** `{source_code, stdin}`. No puede elegir la
imagen, ni las banderas, ni los limites, ni montar nada: todo eso esta fijo en
`docker_runner.py`. Comprometer al `execution-service` permite, como maximo,
pedir que se ejecute un Java — que es lo mismo que ya puede hacer un alumno.

Esto es lo que un socket-proxy NO da: permitir `POST /containers/create` implica
permitir `Privileged: true` y `Binds: ["/:/host"]`, porque esos proxies filtran
por ruta y no por cuerpo del pedido.

## Despliegue

  - Este proceso: con `/var/run/docker.sock` montado.
  - `execution-service`: **SIN** el socket, hablando acá por `RUNNER_URL`.
  - Red: el runner NO debe ser alcanzable desde afuera de la red interna. Su
    unico cliente legitimo es el execution-service.
  - `RUNNER_TOKEN` compartido entre ambos. Sin token configurado el runner
    acepta cualquier llamada — aceptable en desarrollo local, NO en produccion.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from execution_service.config import settings
from execution_service.services.docker_runner import run_java

logger = logging.getLogger(__name__)

# Techo del `docker pull` de arranque. Generoso a proposito: bajar el JDK son
# ~450MB y esto NO esta en el camino de ninguna ejecucion de alumno.
_WARMUP_PULL_TIMEOUT_SECONDS = 600.0


async def _warmup_image() -> None:
    """Baja la imagen del sandbox al arrancar, para que no la baje una corrida.

    `docker_runner.py` aplica el wall-time limit (10s) sobre el `docker run`
    ENTERO. Si la imagen no esta local, ese `docker run` incluye la descarga, y
    la primera corrida de Java tras cada deploy muere por timeout — que ademas
    es indistinguible de un bucle infinito del alumno.

    **Best-effort y en segundo plano**: no bloquea el arranque ni tumba el
    proceso si falla. Sin Docker vivo el runner igual levanta y las corridas dan
    `infrastructure_failure`, que es el camino ya cubierto.

    Deja una ventana residual: si un alumno ejecuta mientras la descarga sigue
    en curso, se sigue comiendo el timeout. Cerrarla del todo pide separar el
    presupuesto de preparacion del contenedor del de ejecucion del codigo, que
    es un cambio de comportamiento del sandbox y va aparte.
    """
    imagen = settings.java_image
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "pull",
            imagen,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _out, err = await asyncio.wait_for(
                proc.communicate(), timeout=_WARMUP_PULL_TIMEOUT_SECONDS
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("warmup_pull_timeout image=%s", imagen)
            return
        if proc.returncode == 0:
            logger.info("warmup_pull_ok image=%s", imagen)
        else:
            logger.warning(
                "warmup_pull_fallo image=%s rc=%s err=%s",
                imagen,
                proc.returncode,
                err.decode("utf-8", errors="replace").strip()[:500],
            )
    except OSError as exc:
        # Sin cliente de Docker en el PATH. No es fatal para el proceso.
        logger.warning("warmup_pull_sin_docker image=%s err=%s", imagen, exc)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    tarea = asyncio.create_task(_warmup_image())
    try:
        yield
    finally:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea


app = FastAPI(
    title="execution-runner",
    description="Ejecuta codigo en contenedores efimeros. Unico componente con acceso a Docker.",
    version="0.1.0",
    lifespan=lifespan,
)


class RunRequest(BaseModel):
    """Lo UNICO que el caller puede decidir.

    No hay campo para la imagen, los limites, la red ni los montajes: eso es
    justamente lo que hace segura esta frontera.
    """

    source_code: str = Field(min_length=1, max_length=100_000)
    stdin: str = Field(default="", max_length=100_000)


def _check_token(token: str | None) -> None:
    if not settings.runner_token:
        # Sin token configurado no se exige nada. Es el modo de desarrollo
        # local; en produccion el token va siempre y el runner no se expone.
        return
    # Comparacion en tiempo constante: comparar con `!=` filtra el token por
    # temporizacion.
    if not token or not secrets.compare_digest(token, settings.runner_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")


@app.post("/run")
async def run(
    req: RunRequest,
    x_runner_token: str | None = Header(default=None),
) -> dict[str, object]:
    _check_token(x_runner_token)
    result = await run_java(req.source_code, req.stdin)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "compile_failed": result.compile_failed,
    }


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}
