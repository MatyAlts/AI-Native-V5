"""Cliente del runner: el execution-service NO toca el socket de Docker.

Cierra el gate D3 del ADR-060.

## El problema

Ejecutar `docker run` requiere acceso a `/var/run/docker.sock`, y ese socket es
**equivalente a root en el host**: con el se puede crear un contenedor
privilegiado que monte `/` y salir a la maquina anfitriona.

Si el `execution-service` lo tuviera montado, comprometerlo daria control total
del servidor — seria peor que el problema que el ADR-060 vino a resolver.

## Por que un socket-proxy NO alcanza

La solucion habitual es poner un proxy del socket que filtre por endpoint. **No
sirve acá**: para lanzar una ejecucion hay que permitir `POST /containers/create`,
y ese endpoint acepta en su cuerpo `Privileged: true` y `Binds: ["/:/host"]`.
Los proxies conocidos filtran por *ruta*, no por *payload*, asi que permitir
crear contenedores es permitir crear uno privilegiado.

## La solucion

No se expone la API de Docker en ninguna forma. Un componente aparte —el
**runner**— recibe unicamente `{source_code, stdin, language}` y construye el
comando el mismo, con la imagen y las banderas fijas en su codigo. `language`
elige entre comandos cerrados (`java` | `python` | `pseint`), no una imagen. El caller
no puede influir en un solo parametro del contenedor.

Comprometer el `execution-service` pasa a permitir, como maximo, **pedir que se
ejecute un Java, un Python o un PSeInt** con las mismas protecciones — que es lo que ya
puede hacer cualquier alumno en el navegador.

El runner es deliberadamente minimo (un endpoint, sin base de datos, sin
dependencias) para que su superficie sea auditable de una sentada. El
`execution-service`, en cambio, tiene auth, Redis, cuotas y un cliente HTTP
hacia el academic-service: mucha mas superficie para tener el socket.

## Alternativa preferible cuando la infraestructura la permita

**Docker rootless** (o Podman). Con el daemon corriendo como usuario sin
privilegios, el socket deja de ser root-equivalente y este servicio podria
volver a invocar Docker directo, eliminando el runner. Verificar con
`docker info | grep -i rootless`. Al 2026-07-29 la maquina de desarrollo corre
Docker como root, por eso existe esta pieza.
"""

from __future__ import annotations

import httpx

from execution_service.config import settings
from execution_service.services.docker_runner import DockerRunResult
from execution_service.services.sandbox_types import SandboxUnavailableError


class LenguajeNoDisponibleError(Exception):
    """El runner no tiene imagen para ese lenguaje (HU-030, N06).

    Hoy solo PSeInt puede faltar: `PSEINT_IMAGE` es opcional. NO es un fallo de
    infraestructura y por eso NO hereda de `SandboxUnavailableError`: la
    corrida sale con todos los casos `skipped` ("sin ejecutar") y la correccion
    sigue, en vez de cortarse como si el sandbox se hubiera caido.
    """

    def __init__(self, language: str) -> None:
        super().__init__(f"lenguaje_no_disponible: {language}")
        self.language = language


# `detail` con el que el runner responde 503 cuando le falta la imagen.
LENGUAJE_NO_DISPONIBLE = "lenguaje_no_disponible"


class RunnerClient:
    """Habla con el runner por HTTP. No conoce Docker."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self._base_url = (base_url or settings.runner_url).rstrip("/")
        self._token = token if token is not None else settings.runner_token
        self._timeout = settings.execution_wall_time_limit_seconds + 15.0

    async def run_java(self, source_code: str, stdin: str = "") -> DockerRunResult:
        """Pide una ejecucion de Java al runner."""
        return await self._run(source_code, stdin, "java")

    async def run_python(self, source_code: str, stdin: str = "") -> DockerRunResult:
        """Pide una ejecucion de Python al runner (HU-015, correccion con IA)."""
        return await self._run(source_code, stdin, "python")

    async def run_pseint(self, source_code: str, stdin: str = "") -> DockerRunResult:
        """Pide una ejecucion de PSeInt al runner (HU-030, correccion con IA).

        Raises:
            LenguajeNoDisponibleError: el runner no tiene `PSEINT_IMAGE`.
        """
        return await self._run(source_code, stdin, "pseint")

    async def _run(self, source_code: str, stdin: str, language: str) -> DockerRunResult:
        """Pide una ejecucion al runner.

        Raises:
            SandboxUnavailableError: el runner no respondio o fallo. Se traduce
                a fallo de infraestructura, nunca a casos fallidos del alumno.
        """
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["X-Runner-Token"] = self._token

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/run",
                    headers=headers,
                    json={"source_code": source_code, "stdin": stdin, "language": language},
                )
        except (httpx.HTTPError, OSError) as exc:
            raise SandboxUnavailableError(f"runner no alcanzable: {type(exc).__name__}") from exc

        if resp.status_code == 503 and _detalle(resp) == LENGUAJE_NO_DISPONIBLE:
            raise LenguajeNoDisponibleError(language)
        if resp.status_code >= 400:
            raise SandboxUnavailableError(f"runner respondio {resp.status_code}")

        body = resp.json()
        return DockerRunResult(
            exit_code=int(body.get("exit_code", -1)),
            stdout=str(body.get("stdout", "")),
            stderr=str(body.get("stderr", "")),
            timed_out=bool(body.get("timed_out", False)),
            compile_failed=bool(body.get("compile_failed", False)),
        )


def _detalle(resp: httpx.Response) -> str | None:
    """El `detail` de un error del runner, o None si no es JSON."""
    try:
        body = resp.json()
    except ValueError:
        return None
    return body.get("detail") if isinstance(body, dict) else None
