"""Cliente del sandbox Judge0 (ADR-059).

Dos responsabilidades y ninguna mas: hablar el protocolo de Judge0 y aplicar los
limites por corrida. La traduccion al formato de casos de prueba del sistema
vive aparte (`result_mapper`), para que el dia que se cambie de sandbox solo se
reescriba este archivo.

**Los limites se mandan SIEMPRE explicitos.** Los defaults de Judge0 son
generosos y cambian entre versiones: heredarlos significa que una actualizacion
del proveedor puede aflojar el techo de CPU de nuestros alumnos sin que nadie se
entere. Es la primera de las dos capas de limite del ADR-059 (la segunda son las
cuotas por alumno, que fallan cerradas).

`enable_network` va SIEMPRE en False y **no es parametro**: es el control C2 del
ADR-059. Sin eso, un ejercicio puede exfiltrar datos, bajar cargas utiles o
atacar terceros desde nuestra identidad.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import IntEnum

import httpx

from execution_service.config import settings


class Judge0Status(IntEnum):
    """Status ids de Judge0. Son estables entre versiones."""

    IN_QUEUE = 1
    PROCESSING = 2
    ACCEPTED = 3
    WRONG_ANSWER = 4
    TIME_LIMIT_EXCEEDED = 5
    COMPILATION_ERROR = 6
    RUNTIME_ERROR_SIGSEGV = 7
    RUNTIME_ERROR_SIGXFSZ = 8
    RUNTIME_ERROR_SIGFPE = 9
    RUNTIME_ERROR_SIGABRT = 10
    RUNTIME_ERROR_NZEC = 11
    RUNTIME_ERROR_OTHER = 12
    INTERNAL_ERROR = 13
    EXEC_FORMAT_ERROR = 14

    @property
    def is_terminal(self) -> bool:
        return self >= Judge0Status.ACCEPTED

    @property
    def is_infra_failure(self) -> bool:
        """Fallo NUESTRO, no del alumno.

        Distinguirlo es el punto de D4 del design: sin esto, una caida del
        sandbox se registra como el alumno fallando todos los casos, y el
        clasificador usa ese conteo para separar dos niveles de apropiacion.
        """
        return self in (Judge0Status.INTERNAL_ERROR, Judge0Status.EXEC_FORMAT_ERROR)


@dataclass(frozen=True)
class Judge0Result:
    status: Judge0Status
    stdout: str
    stderr: str
    compile_output: str
    time_seconds: float | None
    memory_kb: int | None


class Judge0UnavailableError(RuntimeError):
    """El sandbox no respondio. NO es un fallo del codigo del alumno.

    El caller la traduce a un estado de infraestructura, nunca a casos fallidos.
    """


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        # El proveedor puede devolver texto plano si base64_encoded no aplica.
        return value


class Judge0Client:
    def __init__(self, base_url: str | None = None, auth_token: str | None = None) -> None:
        self._base_url = (base_url or settings.judge0_base_url).rstrip("/")
        self._auth_token = auth_token if auth_token is not None else settings.judge0_auth_token
        self._timeout = settings.judge0_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            # Control C3 del ADR-059: el token vive en env, nunca en disco ni en
            # logs. No se loguea esta estructura en ningun lado.
            headers["X-Auth-Token"] = self._auth_token
        return headers

    def _limits(self) -> dict[str, object]:
        return {
            "cpu_time_limit": settings.execution_cpu_time_limit_seconds,
            "wall_time_limit": settings.execution_wall_time_limit_seconds,
            "memory_limit": settings.execution_memory_limit_kb,
            "max_processes_and_or_threads": settings.execution_max_processes,
            # C2 — no es configurable por el caller a proposito.
            "enable_network": settings.execution_enable_network,
        }

    async def submit(
        self,
        *,
        source_code: str,
        language_id: int,
        stdin: str = "",
        expected_output: str | None = None,
    ) -> str:
        """Encola una ejecucion y devuelve su token.

        Raises:
            Judge0UnavailableError: el sandbox no respondio o devolvio un error.
        """
        payload: dict[str, object] = {
            "source_code": base64.b64encode(source_code.encode()).decode(),
            "language_id": language_id,
            "stdin": base64.b64encode(stdin.encode()).decode(),
            **self._limits(),
        }
        if expected_output is not None:
            payload["expected_output"] = base64.b64encode(expected_output.encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/submissions",
                    params={"base64_encoded": "true", "wait": "false"},
                    headers=self._headers(),
                    json=payload,
                )
        except (httpx.HTTPError, OSError) as exc:
            raise Judge0UnavailableError(f"sandbox no alcanzable: {type(exc).__name__}") from exc

        if resp.status_code >= 400:
            raise Judge0UnavailableError(f"sandbox respondio {resp.status_code}")

        token = resp.json().get("token")
        if not token:
            raise Judge0UnavailableError("sandbox no devolvio token")
        return str(token)

    async def get_result(self, token: str) -> Judge0Result:
        """Consulta el resultado de una ejecucion encolada.

        Raises:
            Judge0UnavailableError: el sandbox no respondio o devolvio un error.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/submissions/{token}",
                    params={"base64_encoded": "true"},
                    headers=self._headers(),
                )
        except (httpx.HTTPError, OSError) as exc:
            raise Judge0UnavailableError(f"sandbox no alcanzable: {type(exc).__name__}") from exc

        if resp.status_code >= 400:
            raise Judge0UnavailableError(f"sandbox respondio {resp.status_code}")

        body = resp.json()
        status_id = (body.get("status") or {}).get("id", Judge0Status.INTERNAL_ERROR)
        try:
            status = Judge0Status(status_id)
        except ValueError:
            status = Judge0Status.INTERNAL_ERROR

        raw_time = body.get("time")
        return Judge0Result(
            status=status,
            stdout=_decode(body.get("stdout")),
            stderr=_decode(body.get("stderr")),
            compile_output=_decode(body.get("compile_output")),
            time_seconds=float(raw_time) if raw_time else None,
            memory_kb=body.get("memory"),
        )
