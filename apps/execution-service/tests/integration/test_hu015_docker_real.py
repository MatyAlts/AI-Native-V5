"""Aceptacion HU-015, ronda de arreglos, la parte con Docker REAL (orquestador,
antes de construir; el constructor no la modifica). Juani: "sii dale" (22/11).

C08  Un programa que se pasa del tiempo no deja ningun contenedor vivo, ni en
     Python ni en Java. (H1 de la verificacion del PR #146: `proc.kill()` mataba
     el CLI de `docker run` y el contenedor seguia al 100% de CPU.)
C10  `exit()` / `sys.exit(0)` / `quit()` dan error de ejecucion, igual que en el
     navegador (los dos shims de Pyodide atrapan `BaseException`).

Marcado `integration`: CI corre `-m "not integration"` y sus runners tendrian
que bajar las imagenes dentro del wall time. Se corre a mano:
`pytest apps/execution-service/tests/integration/test_hu015_docker_real.py -m integration`.
Sin Docker FALLA, no se saltea: un skip no es evidencia.
"""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest
from execution_service.config import settings
from execution_service.services import docker_runner
from execution_service.services.docker_runner import to_sandbox_result
from execution_service.services.sandbox_types import SandboxStatus

pytestmark = pytest.mark.integration

JAVA_IMAGE_LOCAL = "eclipse-temurin:21-jdk"
PYTHON_IMAGE_LOCAL = "python:3.12-slim"


# ── utilidades de Docker real ──────────────────────────────────────────


def _vivos(imagen: str) -> list[str]:
    r = subprocess.run(  # noqa: S603 - comando fijo de la prueba, sin entrada externa
        ["docker", "ps", "-q", "--filter", f"ancestor={imagen}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [x for x in r.stdout.split() if x]


def _matar(imagen: str) -> None:
    for cid in _vivos(imagen):
        subprocess.run(  # noqa: S603 - id leido de docker ps
            ["docker", "kill", cid], capture_output=True, check=False
        )


@pytest.fixture
def docker_real(monkeypatch):
    assert shutil.which("docker"), "C08/C10 necesitan Docker real: no se saltean"
    monkeypatch.setattr(settings, "python_image", PYTHON_IMAGE_LOCAL)
    monkeypatch.setattr(settings, "java_image", JAVA_IMAGE_LOCAL)
    for img in (PYTHON_IMAGE_LOCAL, JAVA_IMAGE_LOCAL):
        _matar(img)
    yield
    # Pase lo que pase, la prueba no deja nada quemando CPU.
    for img in (PYTHON_IMAGE_LOCAL, JAVA_IMAGE_LOCAL):
        _matar(img)


def _esperar_sin_contenedores(imagen: str, segundos: float = 8.0) -> list[str]:
    limite = time.monotonic() + segundos
    vivos = _vivos(imagen)
    while vivos and time.monotonic() < limite:
        time.sleep(0.5)
        vivos = _vivos(imagen)
    return vivos


# ── C08 ────────────────────────────────────────────────────────────────


async def test_c08_python_que_se_pasa_del_tiempo_no_deja_contenedor(
    docker_real, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "execution_wall_time_limit_seconds", 3.0)
    r = await docker_runner.run_python("while True:\n    pass", "")
    assert r.timed_out is True
    vivos = _esperar_sin_contenedores(PYTHON_IMAGE_LOCAL)
    assert vivos == [], f"quedaron contenedores de Python vivos: {vivos}"


async def test_c08_java_que_se_pasa_del_tiempo_no_deja_contenedor(docker_real, monkeypatch) -> None:
    # javac tarda unos segundos: el limite tiene que alcanzar para compilar y
    # entrar al bucle, y aun asi cortarlo.
    monkeypatch.setattr(settings, "execution_wall_time_limit_seconds", 8.0)
    codigo = "public class Main { public static void main(String[] a) { while (true) {} } }"
    r = await docker_runner.run_java(codigo, "")
    assert r.timed_out is True
    vivos = _esperar_sin_contenedores(JAVA_IMAGE_LOCAL)
    assert vivos == [], f"quedaron contenedores de Java vivos: {vivos}"


async def test_c08_una_corrida_normal_sigue_andando(docker_real) -> None:
    r = await docker_runner.run_python("n = int(input())\nprint(n * 2)", "3")
    assert r.timed_out is False
    assert r.stdout == "6\n"
    assert _esperar_sin_contenedores(PYTHON_IMAGE_LOCAL, 3.0) == []


# ── C10 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("salida", ["exit()", "import sys\nsys.exit(0)", "quit()"])
async def test_c10_exit_es_error_como_en_el_navegador(docker_real, salida: str) -> None:
    r = await docker_runner.run_python(f"print(6)\n{salida}", "")
    resultado = to_sandbox_result(r, "6")
    assert resultado.status is not SandboxStatus.ACCEPTED, (
        f"{salida!r} aprueba en el servidor y falla en el Probar del alumno"
    )
    assert resultado.status.name.startswith("RUNTIME_ERROR")
    assert _esperar_sin_contenedores(PYTHON_IMAGE_LOCAL, 3.0) == []


async def test_c10_un_programa_que_termina_normal_sigue_aprobando(docker_real) -> None:
    r = await docker_runner.run_python("print(6)", "")
    assert to_sandbox_result(r, "6").status is SandboxStatus.ACCEPTED
