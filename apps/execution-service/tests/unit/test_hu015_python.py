"""Aceptacion HU-015, tramo 2 (orquestador, antes de construir; el constructor
no la modifica). Criterios aprobados por Juani el 22/11/2026 ("sisi apruebo").

El sandbox pasa a ejecutar Python, para que la correccion con IA tenga el
resultado real de cada caso. El "Probar" del alumno sigue en Pyodide (N04).

Contrato que fija esta prueba:
  - `executor.LENGUAJES_SOPORTADOS` incluye "python".
  - `RunnerClient.run_python(source_code, stdin)` -> `DockerRunResult`, y
    `run_cases` la usa para los ejercicios de Python.
  - `docker_runner.run_python(source_code, stdin)` lanza `docker run` con las
    mismas banderas de aislamiento que Java y la imagen `settings.python_image`.
  - El runner acepta `language: "java" | "python"` (default "java") en `/run`.
  - En produccion el runner no arranca con `PYTHON_IMAGE` por tag.

C04  Python corre con las mismas protecciones que Java.
C05  Misma comparacion de salida: correcto pasa, error tipico falla.
C06  `input()` lee el stdin del caso.
N03  Los casos ocultos de Python no muestran entrada, esperada ni salida.
N05  Un Python que termina con `sys.exit(101)` no es un error de compilacion.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from execution_service import runner_main
from execution_service.config import settings
from execution_service.services import docker_runner, executor
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.docker_runner import DockerRunResult
from execution_service.services.executor import run_cases, to_client_payload
from execution_service.services.result_mapper import CaseStatus
from execution_service.services.runner_client import RunnerClient

BANDERAS = [
    "--network=none",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--read-only",
    "--log-driver=none",
]


def _tc(i: int, stdin: str, expected: str, publico: bool = True) -> TestCase:
    return TestCase(
        id=f"t{i}",
        name=f"caso {i}",
        type="stdin_stdout",
        code=stdin,
        expected=expected,
        is_public=publico,
        weight=1.0,
    )


def _ejercicio(cases: list[TestCase]) -> Ejercicio:
    return Ejercicio(id=uuid4(), language="python", inicial_codigo=None, test_cases=cases)


def _ok(stdout: str, code: int = 0, stderr: str = "") -> DockerRunResult:
    return DockerRunResult(
        exit_code=code, stdout=stdout, stderr=stderr, timed_out=False, compile_failed=False
    )


class _RunnerFalso:
    """Ejecuta "n*2" sobre el stdin: el doble que un Python correcto daria."""

    llamadas: list[tuple[str, str]] = []

    def __init__(self, *a, **k) -> None:
        pass

    async def run_python(self, source_code: str, stdin: str = "") -> DockerRunResult:
        _RunnerFalso.llamadas.append((source_code, stdin))
        factor = 3 if "n * 3" in source_code else 2
        return _ok(f"{int(stdin) * factor}\n")

    async def run_java(self, source_code: str, stdin: str = "") -> DockerRunResult:
        raise AssertionError("un ejercicio de Python no puede ir al runner de Java")


@pytest.fixture
def runner_falso(monkeypatch):
    _RunnerFalso.llamadas = []
    monkeypatch.setattr(executor, "RunnerClient", _RunnerFalso)
    return _RunnerFalso


# ── C04 ────────────────────────────────────────────────────────────────


def test_c04_python_es_un_lenguaje_soportado() -> None:
    assert "python" in executor.LENGUAJES_SOPORTADOS
    assert "java" in executor.LENGUAJES_SOPORTADOS


@pytest.mark.asyncio
async def test_c04_python_corre_con_las_mismas_banderas_que_java(monkeypatch) -> None:
    capturado: dict[str, list[str]] = {}

    class _Proc:
        returncode = 0

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            capturado["stdin"] = [data.decode()]
            return b"6\n", b""

        def kill(self) -> None:
            pass

        async def wait(self) -> int:
            return 0

    async def _fake(*args, **kwargs):
        capturado["args"] = [str(a) for a in args]
        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)
    assert hasattr(docker_runner, "run_python"), "falta docker_runner.run_python"
    assert hasattr(settings, "python_image"), "falta settings.python_image"
    r = await docker_runner.run_python("n = int(input())\nprint(n * 2)", "3")

    args = capturado["args"]
    for bandera in BANDERAS:
        assert bandera in args, bandera
    assert any(a.startswith("--user=") and a != "--user=0" and "root" not in a for a in args)
    assert settings.python_image in args
    assert settings.java_image not in args
    assert capturado["stdin"] == ["3"]
    assert r.stdout == "6\n"
    assert r.compile_failed is False


def test_c04_en_produccion_python_image_por_tag_no_arranca(monkeypatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "runner_token", "x" * 40)
    monkeypatch.setattr(settings, "java_image", "eclipse-temurin@sha256:" + "a" * 64)
    assert "python_image" in type(settings).model_fields, "falta settings.python_image"
    monkeypatch.setattr(settings, "python_image", "python:3.12-slim")
    problemas = runner_main.verificar_configuracion_segura()
    assert any("PYTHON_IMAGE" in p for p in problemas), problemas

    monkeypatch.setattr(settings, "python_image", "python@sha256:" + "b" * 64)
    assert runner_main.verificar_configuracion_segura() == []


# ── C05 / C06 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c05_un_python_correcto_pasa_todos_los_casos(runner_falso) -> None:
    ej = _ejercicio([_tc(0, "3", "6"), _tc(1, "10", "20", publico=False)])
    run = await run_cases(source_code="n = int(input())\nprint(n * 2)", ejercicio=ej)
    assert [c.status for c in run.cases] == [CaseStatus.PASS, CaseStatus.PASS]
    assert (run.total, run.passed, run.failed) == (2, 2, 0)


@pytest.mark.asyncio
async def test_c05_un_error_tipico_falla_su_caso(runner_falso) -> None:
    ej = _ejercicio([_tc(0, "3", "6")])
    run = await run_cases(source_code="n = int(input())\nprint(n * 3)", ejercicio=ej)
    assert run.cases[0].status is CaseStatus.FAIL
    assert run.cases[0].got == "9\n"


@pytest.mark.asyncio
async def test_c06_cada_caso_recibe_su_stdin(runner_falso) -> None:
    ej = _ejercicio([_tc(0, "3", "6"), _tc(1, "10", "20")])
    await run_cases(source_code="n = int(input())\nprint(n * 2)", ejercicio=ej)
    assert [stdin for _, stdin in runner_falso.llamadas] == ["3", "10"]


@pytest.mark.asyncio
async def test_c06_el_runner_recibe_el_lenguaje(monkeypatch) -> None:
    enviado: dict = {}

    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {"exit_code": 0, "stdout": "6\n", "stderr": "", "timed_out": False,
                    "compile_failed": False}

    class _Cliente:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url, headers=None, json=None):
            enviado["json"] = json
            return _Resp()

    import execution_service.services.runner_client as rc

    monkeypatch.setattr(rc.httpx, "AsyncClient", _Cliente)
    assert hasattr(RunnerClient, "run_python"), "falta RunnerClient.run_python"
    r = await RunnerClient(base_url="http://runner", token="t").run_python("print(6)", "3")
    assert enviado["json"]["language"] == "python"
    assert enviado["json"]["stdin"] == "3"
    assert r.stdout == "6\n"


def test_c06_el_runner_por_defecto_sigue_siendo_java() -> None:
    req = runner_main.RunRequest(source_code="class Main {}")
    assert getattr(req, "language", None) == "java"
    py = runner_main.RunRequest(source_code="print(1)", language="python")
    assert getattr(py, "language", None) == "python"
    with pytest.raises(Exception):
        runner_main.RunRequest(source_code="x", language="bash")


# ── N03 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n03_los_ocultos_de_python_no_filtran(runner_falso) -> None:
    ej = _ejercicio([_tc(0, "3", "6"), _tc(1, "777", "1554", publico=False)])
    run = await run_cases(source_code="n = int(input())\nprint(n * 2)", ejercicio=ej)
    cable = json.dumps(to_client_payload(run, ej))
    assert "777" not in cable
    assert "1554" not in cable


# ── N05 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n05_sys_exit_101_en_python_no_es_error_de_compilacion(monkeypatch) -> None:
    class _Proc:
        returncode = 101

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            return b"", b""

        def kill(self) -> None:
            pass

        async def wait(self) -> int:
            return 101

    async def _fake(*args, **kwargs):
        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)
    assert hasattr(docker_runner, "run_python"), "falta docker_runner.run_python"
    r = await docker_runner.run_python("import sys\nsys.exit(101)", "")
    assert r.compile_failed is False
    assert r.exit_code == 101
