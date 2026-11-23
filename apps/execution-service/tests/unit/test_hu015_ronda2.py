"""Aceptacion HU-015, ronda de arreglos, la parte sin Docker (orquestador,
antes de construir; el constructor no la modifica). Juani: "sii dale" (22/11).
La parte con Docker real (C08 y C10) esta en
`tests/integration/test_hu015_docker_real.py`.

C09  Los casos `pytest_assert` de Python se saltean en el servidor: no llegan
     al runner y quedan `skipped` (la correccion los muestra como no
     ejecutados). Los `stdin_stdout` del mismo ejercicio si corren.
C11  El servidor no ejecuta Python dentro de un episodio del alumno: con
     `episode_id` no se llama al runner ni se emite `tests_ejecutados`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from execution_service.auth import User
from execution_service.routes import executions as ruta
from execution_service.services import executor
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.docker_runner import DockerRunResult
from execution_service.services.executor import run_cases
from execution_service.services.result_mapper import CaseStatus

# ── C09 ────────────────────────────────────────────────────────────────


def _tc(i: int, tipo: str, code: str, expected: str | None) -> TestCase:
    return TestCase(
        id=f"t{i}",
        name=f"caso {i}",
        type=tipo,
        code=code,
        expected=expected,
        is_public=True,
        weight=1.0,
    )


class _RunnerEspia:
    llamadas: list[tuple[str, str]] = []

    def __init__(self, *a, **k) -> None:
        pass

    async def run_python(self, source_code: str, stdin: str = "") -> DockerRunResult:
        _RunnerEspia.llamadas.append((source_code, stdin))
        return DockerRunResult(
            exit_code=0, stdout="6\n", stderr="", timed_out=False, compile_failed=False
        )

    async def run_java(self, source_code: str, stdin: str = "") -> DockerRunResult:
        raise AssertionError("no es Java")


@pytest.fixture
def runner_espia(monkeypatch):
    _RunnerEspia.llamadas = []
    monkeypatch.setattr(executor, "RunnerClient", _RunnerEspia)
    return _RunnerEspia


async def test_c09_pytest_assert_de_python_se_saltea(runner_espia) -> None:
    ej = Ejercicio(
        id=uuid4(),
        language="python",
        inicial_codigo=None,
        test_cases=[_tc(0, "pytest_assert", "assert doble(3) == 6", None)],
    )
    run = await run_cases(source_code="def doble(n):\n    return n * 3", ejercicio=ej)
    assert [c.status for c in run.cases] == [CaseStatus.SKIPPED]
    assert run_cases is not None and runner_espia.llamadas == []
    assert run.total == 0


async def test_c09_los_stdin_stdout_del_mismo_ejercicio_si_corren(runner_espia) -> None:
    ej = Ejercicio(
        id=uuid4(),
        language="python",
        inicial_codigo=None,
        test_cases=[
            _tc(0, "stdin_stdout", "3", "6"),
            _tc(1, "pytest_assert", "assert doble(3) == 6", None),
        ],
    )
    run = await run_cases(source_code="n = int(input())\nprint(n * 2)", ejercicio=ej)
    assert [c.status for c in run.cases] == [CaseStatus.PASS, CaseStatus.SKIPPED]
    assert [stdin for _, stdin in runner_espia.llamadas] == ["3"]
    assert (run.total, run.passed, run.failed) == (1, 1, 0)


# ── C11 ────────────────────────────────────────────────────────────────


def _usuario() -> User:
    return User(
        id=uuid4(),
        tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alumno@utn.edu.ar",
        roles=frozenset({"estudiante", "docente"}),
    )


class _Espia:
    def __init__(self) -> None:
        self.emitidos: list[dict[str, Any]] = []
        self.guardado: dict[str, Any] | None = None


@pytest.fixture
def espia(monkeypatch) -> _Espia:
    s = _Espia()

    class _Tutor:
        async def emit_tests_ejecutados(self, **kwargs: Any) -> bool:
            s.emitidos.append(kwargs)
            return True

    async def _put(execution_id: UUID, **kwargs: Any) -> None:
        if kwargs.get("result") is not None:
            s.guardado = kwargs["result"]

    monkeypatch.setattr(ruta, "TutorClient", _Tutor)
    monkeypatch.setattr(ruta.execution_store, "put", _put)
    return s


def _academic(ejercicio: Ejercicio):
    class _Client:
        async def get_ejercicio(self, ejercicio_id: UUID, tenant_id: UUID) -> Ejercicio:
            return ejercicio

    return _Client


async def _correr(monkeypatch, ejercicio: Ejercicio, episode_id: UUID | None) -> None:
    monkeypatch.setattr(ruta, "AcademicClient", _academic(ejercicio))
    req = ruta.ExecutionRequest(
        ejercicio_id=ejercicio.id,
        source_code="n = int(input())\nprint(n * 2)",
        episode_id=episode_id,
    )
    await ruta._run_and_store(uuid4(), req=req, user=_usuario())


def _ej_python() -> Ejercicio:
    return Ejercicio(
        id=uuid4(),
        language="python",
        inicial_codigo=None,
        test_cases=[_tc(0, "stdin_stdout", "3", "6")],
    )


async def test_c11_python_dentro_de_un_episodio_no_se_ejecuta_ni_emite(
    monkeypatch, espia, runner_espia
) -> None:
    await _correr(monkeypatch, _ej_python(), episode_id=uuid4())
    assert runner_espia.llamadas == [], "el servidor ejecuto Python dentro de un episodio"
    assert espia.emitidos == [], "se emitio tests_ejecutados de Python server-side"


async def test_c11_python_sin_episodio_si_se_ejecuta(monkeypatch, espia, runner_espia) -> None:
    await _correr(monkeypatch, _ej_python(), episode_id=None)
    assert [stdin for _, stdin in runner_espia.llamadas] == ["3"]
    assert espia.guardado is not None and espia.guardado["passed"] == 1
    assert espia.emitidos == []
