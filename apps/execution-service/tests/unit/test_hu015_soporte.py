"""Pruebas de apoyo del constructor para HU-015 (no son la aceptacion).

Cubren lo que la aceptacion no fija y que el cambio podia romper de costado:
el comando de Java no cambia, `run_libre` no le manda Python al comando de
Java, y el prompt de `input()` no entra a la salida comparada (paridad con el
shim de Pyodide).
"""

from __future__ import annotations

import pytest
from execution_service.config import settings
from execution_service.services import docker_runner, executor
from execution_service.services.docker_runner import DockerRunResult

COMANDO_JAVA = 'printf %s "$SRC" > Main.java && javac Main.java 2>&1 || exit 101; java Main'


def test_el_comando_de_java_no_cambio() -> None:
    args = docker_runner._docker_args("class Main {}")
    assert args[-3:] == ["sh", "-c", COMANDO_JAVA]
    assert args[-4] == settings.java_image
    assert not any(a.startswith("PRELUDIO=") for a in args)


def test_python_usa_su_imagen_y_el_preludio() -> None:
    args = docker_runner._docker_args_python("print(1)")
    assert args[args.index(settings.python_image) + 1 : args.index(settings.python_image) + 3] == [
        "sh",
        "-c",
    ]
    assert f"PRELUDIO={docker_runner._PRELUDIO_PYTHON}" in args
    assert "SRC=print(1)" in args


def test_el_preludio_no_imprime_el_prompt(capsys, monkeypatch, tmp_path) -> None:
    """Se ejecuta el preludio real sobre un main.py, con stdin falso."""
    import io
    import sys

    (tmp_path / "main.py").write_text('n = int(input("Ingrese n: "))\nprint(n * 2)\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("3"))
    import builtins

    original = builtins.input
    try:
        # Es el preludio propio del modulo, no codigo externo.
        exec(docker_runner._PRELUDIO_PYTHON, {})  # noqa: S102
    finally:
        builtins.input = original
    assert capsys.readouterr().out == "6\n"


class _RunnerEspia:
    llamado: list[str] = []

    def __init__(self, *a, **k) -> None:
        pass

    async def run_java(self, source_code: str, stdin: str = "") -> DockerRunResult:
        _RunnerEspia.llamado.append("java")
        return DockerRunResult(0, "", "", False, False)

    async def run_python(self, source_code: str, stdin: str = "") -> DockerRunResult:
        _RunnerEspia.llamado.append("python")
        return DockerRunResult(0, "", "", False, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["python", "java"])
async def test_run_libre_despacha_por_lenguaje(monkeypatch, language) -> None:
    _RunnerEspia.llamado = []
    monkeypatch.setattr(executor, "RunnerClient", _RunnerEspia)
    libre = await executor.run_libre(source_code="x", language=language)
    assert libre.ejecutado is True
    assert _RunnerEspia.llamado == [language]
