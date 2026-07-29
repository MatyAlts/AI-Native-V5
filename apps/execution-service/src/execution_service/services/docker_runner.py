"""SPIKE — ejecucion de Java en un contenedor Docker plano, sin Judge0.

**Esto es un spike, no una decision tomada.** Existe para medir si el camino
"Docker directo" es viable y con que numeros, antes de enmendar el ADR-059 (que
Cortez firmo eligiendo Judge0 gestionado).

## Por que se explora

Judge0 resulto tener dos costos que el ADR no anticipo del todo:

  - `isolate` exige **cgroups v1**. Las distros modernas traen v2, asi que no
    levanta ni en la maquina de desarrollo ni en un VPS reciente sin tocar GRUB.
  - Exige **contenedor privilegiado**, que es lo que obliga a sacarlo del VPS de
    produccion (D2 del ADR) y por lo tanto a pagar cloud o un servidor aparte.

Un `docker run` plano no tiene ninguno de los dos problemas: anda con cgroups
v2 y **no necesita privilegios**. El aislamiento pasa a ser el de Docker — el
mismo que la plataforma ya usa para sus 12 servicios — en vez de una superficie
nueva.

## Lo que este spike NO resuelve

**Quien puede invocar `docker run`.** Si el execution-service monta
`/var/run/docker.sock`, eso equivale a root en el host y seria peor que el
problema original. Las salidas son un socket-proxy que solo permita `run` sobre
una imagen fija, o correr esta pieza fuera de contenedor. Se decide si el spike
prospera.

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
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from execution_service.config import settings

# Imagen con JDK. Pineada por digest en produccion; para el spike alcanza el tag.
JAVA_IMAGE = "eclipse-temurin:21-jdk"

# Usuario sin privilegios dentro del contenedor. 65534 = nobody.
CONTAINER_USER = "65534:65534"


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
        JAVA_IMAGE,
        "sh",
        "-c",
        # Se compila y ejecuta en /work (tmpfs). El exit code 101 se reserva
        # para "no compilo", que es distinto de "el programa fallo".
        "cp /src/Main.java . && javac Main.java 2>&1 || exit 101; java Main",
    ]


async def run_java(source_code: str, stdin: str = "") -> DockerRunResult:
    """Compila y ejecuta un archivo Java unico en un contenedor aislado."""
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
