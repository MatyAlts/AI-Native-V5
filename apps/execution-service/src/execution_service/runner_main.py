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
    unico cliente legitimo es el execution-service. Es lo unico de los tres
    controles que el codigo no puede garantizar solo — se verifica sobre el
    despliegue con `scripts/verificar-despliegue-ejecucion.sh`.
  - `RUNNER_TOKEN` compartido entre ambos, e imagen pineada por digest. Fuera de
    desarrollo los dos son OBLIGATORIOS: sin ellos el proceso **no arranca**
    (ver `verificar_configuracion_segura`). Antes fallaban abiertos, que es
    justo el modo de falla que el ADR-060 no puede permitirse.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
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


class ArranqueInseguroError(RuntimeError):
    """El runner no arranca con una configuracion que el ADR-060 prohibe."""


def _es_produccion() -> bool:
    return settings.environment.strip().lower() not in {"development", "dev", "test", "testing"}


def verificar_configuracion_segura() -> list[str]:
    """Controles del ADR-060 que en produccion se EXIGEN, no se recuerdan.

    Devuelve la lista de problemas. Vacia = configuracion aceptable.

    Estos dos controles (tarea 8.4) estaban fallando ABIERTOS: sin
    `RUNNER_TOKEN` el runner atendia a cualquiera, y con la imagen por tag
    corria lo que hubiera del otro lado del tag ese dia. Un control que se
    cumple solo si alguien se acordo de configurarlo no es un control — el
    ADR-059 ya dejo esa leccion cuando dio por sentado que Judge0 levantaba.

    Se verifica al arrancar y no por request: si esta mal, no hay que atender
    ni una sola corrida.
    """
    problemas: list[str] = []

    # C3 — El token es la unica barrera real. El runner es el UNICO componente
    # con acceso al socket de Docker: permitir `POST /containers/create` es
    # permitir crear un contenedor privilegiado con `/` montado (ADR-060 D3).
    # Que ademas no sea alcanzable desde afuera es defensa en profundidad, pero
    # esto es el candado.
    if not settings.runner_token:
        problemas.append(
            "RUNNER_TOKEN vacio: el runner atenderia /run a cualquiera que lo alcance, "
            "y es el unico proceso con acceso al socket de Docker (ADR-060 D3)."
        )
    elif len(settings.runner_token) < 32:
        problemas.append(
            f"RUNNER_TOKEN de {len(settings.runner_token)} chars: usar >=32 "
            "(`openssl rand -base64 32`)."
        )

    # C1 — Un tag es mutable: `21-jdk` de hoy no es el de manana. Para un
    # sandbox que ejecuta codigo de terceros, el digest es lo que hace
    # reproducible QUE se corrio — y es parte de la defensa de la tesis, no
    # solo higiene operativa.
    if "@sha256:" not in settings.java_image:
        problemas.append(
            f"JAVA_IMAGE por tag mutable ({settings.java_image}): pinear por digest. "
            "Obtenerlo con `docker inspect --format='{{index .RepoDigests 0}}' <imagen>`."
        )
    else:
        # El digest se valida ENTERO. Preguntar solo por el substring `@sha256:`
        # dejaba pasar un digest cortado: el 2026-08-05 produccion corria con 55
        # de 64 caracteres, el runner arrancaba sin chistar y toda corrida moria
        # despues, en el `docker run`. Un control que un valor roto satisface no
        # es un control — y este el ADR-060 lo declara falla-cerrado.
        digest = settings.java_image.split("@sha256:", 1)[1]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            problemas.append(
                f"JAVA_IMAGE con digest mal formado ({len(digest)} chars, deberian ser 64 "
                "hex): se corta al pegarlo. Verificar con `docker images --digests <imagen>`."
            )

    return problemas


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    problemas = verificar_configuracion_segura()
    if problemas:
        detalle = "\n".join(f"  - {p}" for p in problemas)
        if _es_produccion():
            # Fallar CERRADO, igual que las cuotas: sin la garantia, no se
            # atiende. Arrancar igual seria exactamente el modo de falla que
            # este chequeo existe para impedir.
            raise ArranqueInseguroError(
                f"El runner no arranca en '{settings.environment}' con esta configuracion:\n"
                f"{detalle}\n"
                "Son controles obligatorios del ADR-060 (tarea 8.4)."
            )
        logger.warning(
            "runner_configuracion_insegura entorno=%s (tolerado fuera de produccion):\n%s",
            settings.environment,
            detalle,
        )

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
        # En produccion esto es inalcanzable: `verificar_configuracion_segura`
        # impide arrancar sin token. Se chequea igual — es el unico proceso con
        # el socket de Docker, y un fail-open aca es acceso al host. Defensa en
        # profundidad barata contra un arranque que esquive el lifespan.
        if _es_produccion():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Runner mal configurado: sin RUNNER_TOKEN",
            )
        # Fuera de produccion no se exige nada: es el modo de desarrollo local.
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
