"""Ejecucion de Java en un contenedor Docker efimero, sin privilegios (ADR-060).

Motor de ejecucion del servicio. Reemplaza a Judge0, que quedo superado por el
ADR-060 tras medir el spike.

## Por que se cambio

Judge0 resulto tener dos costos que el ADR no anticipo del todo:

  - `isolate` exige **cgroups v1**. Las distros modernas traen v2, asi que no
    levanta ni en la maquina de desarrollo ni en un VPS reciente sin tocar GRUB.
  - Exige **contenedor privilegiado**, que es lo que obliga a sacarlo del VPS de
    produccion (D2 del ADR) y por lo tanto a pagar cloud o un servidor aparte.

Un `docker run` plano no tiene ninguno de los dos problemas: anda con cgroups
v2 y **no necesita privilegios**. El aislamiento pasa a ser el de Docker — el
mismo que la plataforma ya usa para sus 12 servicios — en vez de una superficie
nueva.

## Lo que este modulo NO resuelve

**Quien puede invocar `docker run`.** Si el execution-service monta
`/var/run/docker.sock`, eso equivale a root en el host y seria peor que el
problema original. Las salidas son un socket-proxy que solo permita `run` sobre
una imagen fija, o correr esta pieza fuera de contenedor. Es el gate del ADR-060:
hasta que este resuelto, la ejecucion NO se habilita en produccion.

## Controles aplicados

Todos desde el arranque, no agregados despues:

  --network=none              sin salida de red (control C2 del ADR-059)
  --read-only + tmpfs         sin escritura al filesystem salvo /tmp acotado
  --cap-drop=ALL              sin capabilities
  --security-opt no-new-privileges   no puede escalar via setuid
  --user                      no corre como root dentro del contenedor
  --memory / --cpus / --pids-limit   limites por corrida, explicitos
  timeout externo             `docker run` tambien se puede colgar
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from execution_service.config import settings
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus

logger = logging.getLogger(__name__)

# La imagen sale de config: en produccion se pinea por digest (control C1).

# Usuario sin privilegios dentro del contenedor. 65534 = nobody.
CONTAINER_USER = "65534:65534"

# ── Techo de corridas simultaneas ────────────────────────────────────────────
#
# Sin esto, N alumnos apretando "Ejecutar" a la vez lanzan N contenedores a la
# vez. Compilar Java es CPU-bound, asi que se pelean por los cores del host y
# cada corrida tarda mas — hasta pasarse del wall-time y morir por timeout.
#
# Medido sobre 4 CPUs (el hardware del VPS), con la imagen ya bajada:
#
#     30 concurrentes -> 8,3 s, 30/30 ok   (83% del presupuesto de 10 s)
#     40 concurrentes -> 28 de 40 MUEREN por timeout
#     60 concurrentes -> mueren las 60
#
# No degrada suave: se cae de golpe entre 30 y 40.
#
# Y el modo de falla es peor que "lento". Un timeout por contencion del host es
# INDISTINGUIBLE de un bucle infinito del alumno: los dos devuelven
# `timed_out=True` -> `CaseStatus.ERROR` -> cuenta como fallo -> N3. O sea que
# bajo carga, alumnos que escribieron codigo correcto quedan registrados en el
# corpus como que fallaron, por culpa del servidor. Es el mismo problema que
# `ctr_emitter` evita para el fallo de infraestructura, deflactando en vez de
# inflar — y tampoco se nota, porque el evento se ve igual que uno legitimo.
#
# Con el techo puesto, el excedente ESPERA en vez de morir. Esperar unos
# segundos es honesto; fallar y quedar mal anotado en el corpus, no. El endpoint
# ya es asincrono con consulta de estado (D2), asi que la espera no congela nada
# del lado del alumno.
#
# El techo vive ACA y no en el execution-service a proposito: este modulo corre
# dentro del runner, que es el unico componente con acceso al socket de Docker
# (ADR-060 D3). Es el unico punto por el que pasan todas las corridas — un
# limite en el servicio no se sostendria con mas de una replica.
_semaforo: asyncio.Semaphore | None = None


def _obtener_semaforo() -> asyncio.Semaphore:
    """Semaforo perezoso: se crea en el loop que corre, no al importar."""
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(settings.execution_max_concurrent_runs)
    return _semaforo


@dataclass(frozen=True)
class DockerRunResult:
    """Resultado crudo de una corrida. Se mapea al formato del sistema aparte."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    compile_failed: bool


def _docker_args(workdir: Path) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        # C2 del ADR-059: el codigo del alumno NO tiene salida de red.
        "--network=none",
        f"--memory={settings.execution_memory_limit_kb}k",
        f"--cpus={settings.execution_cpu_time_limit_seconds / 5:.2f}",
        f"--pids-limit={settings.execution_max_processes}",
        "--read-only",
        # Escribible pero acotado: javac necesita escribir los .class. `mode=1777`
        # es lo que hace falta para que el usuario sin privilegios pueda escribir
        # — el tmpfs se monta como root y sin esto `cp` da "Permission denied".
        "--tmpfs=/work:rw,size=64m,exec,mode=1777",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--user={CONTAINER_USER}",
        "-v",
        f"{workdir}:/src:ro",
        "-w",
        "/work",
        settings.java_image,
        "sh",
        "-c",
        # Se compila y ejecuta en /work (tmpfs). El exit code 101 se reserva
        # para "no compilo", que es distinto de "el programa fallo".
        "cp /src/Main.java . && javac Main.java 2>&1 || exit 101; java Main",
    ]


async def run_java(source_code: str, stdin: str = "") -> DockerRunResult:
    """Compila y ejecuta un archivo Java unico en un contenedor aislado.

    Espera turno si ya hay `execution_max_concurrent_runs` corridas en vuelo.
    La espera NO consume el wall-time del alumno: el cronometro arranca recien
    cuando se lanza el contenedor. Es la diferencia entre encolar y fallar.
    """
    semaforo = _obtener_semaforo()
    if semaforo.locked():
        logger.info(
            "sandbox_saturado techo=%s — la corrida espera turno",
            settings.execution_max_concurrent_runs,
        )
    async with semaforo:
        return await _run_java_sin_techo(source_code, stdin)


async def _run_java_sin_techo(source_code: str, stdin: str = "") -> DockerRunResult:
    """El cuerpo real. Separado para que el wall-time NO cuente la espera."""
    tmpdir = Path(tempfile.mkdtemp(prefix="exec-"))
    try:
        (tmpdir / "Main.java").write_text(source_code, encoding="utf-8")
        # El directorio tiene que ser legible por el usuario del contenedor.
        tmpdir.chmod(0o755)
        (tmpdir / "Main.java").chmod(0o644)

        proc = await asyncio.create_subprocess_exec(
            *_docker_args(tmpdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(stdin.encode()),
                timeout=settings.execution_wall_time_limit_seconds,
            )
        except TimeoutError:
            # `docker run` tambien se puede colgar: el limite del contenedor no
            # cubre el caso de que el daemon no responda.
            proc.kill()
            await proc.wait()
            return DockerRunResult(
                exit_code=-1, stdout="", stderr="", timed_out=True, compile_failed=False
            )

        code = proc.returncode or 0
        return DockerRunResult(
            exit_code=code,
            stdout=out.decode("utf-8", errors="replace"),
            stderr=err.decode("utf-8", errors="replace"),
            timed_out=False,
            # 101 es el codigo que el comando reserva para fallo de compilacion.
            compile_failed=code == 101,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def to_sandbox_result(run: DockerRunResult, expected_output: str | None) -> SandboxResult:
    """Traduce la corrida cruda al tipo comun del servicio.

    La comparacion contra `expected_output` se hace acá y no en el contenedor: el
    contenedor solo ejecuta, la evaluacion es nuestra. Judge0 lo hacia adentro;
    hacerlo afuera es mas simple de auditar.
    """
    if run.timed_out:
        return SandboxResult(
            status=SandboxStatus.TIME_LIMIT_EXCEEDED,
            stdout=run.stdout,
            stderr=run.stderr,
            compile_output="",
            time_seconds=settings.execution_wall_time_limit_seconds,
            memory_kb=None,
        )

    if run.compile_failed:
        return SandboxResult(
            status=SandboxStatus.COMPILATION_ERROR,
            stdout="",
            stderr="",
            # javac escribe a stdout por como se arma el comando.
            compile_output=run.stdout or run.stderr,
            time_seconds=None,
            memory_kb=None,
        )

    if run.exit_code != 0:
        # El programa compilo pero termino mal: excepcion, exit() distinto de 0,
        # o lo mato el limite de memoria.
        return SandboxResult(
            status=SandboxStatus.RUNTIME_ERROR_NZEC,
            stdout=run.stdout,
            stderr=run.stderr,
            compile_output="",
            time_seconds=None,
            memory_kb=None,
        )

    # Corrio bien. Si el caso declara salida esperada, se compara normalizando
    # espacios de los bordes — mismo criterio que el runner de Pyodide.
    if expected_output is not None:
        ok = run.stdout.strip() == expected_output.strip()
        status = SandboxStatus.ACCEPTED if ok else SandboxStatus.WRONG_ANSWER
    else:
        # Sin `expected` no hay nada que comparar: que haya terminado con exito
        # es el criterio (caso `junit_assert`, donde el assert que falla hace
        # que el programa termine con codigo distinto de cero).
        status = SandboxStatus.ACCEPTED

    return SandboxResult(
        status=status,
        stdout=run.stdout,
        stderr=run.stderr,
        compile_output="",
        time_seconds=None,
        memory_kb=None,
    )
