"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica). Criterios acordados con Juani el 24/11/2026.

PSeInt corre en el navegador para el alumno (como Python) y en el servidor
SOLO para la correccion con IA (como Python desde HU-015), con una imagen
propia que trae el mismo interprete (`packages/pseint`, punto de entrada
`node /opt/pseint/run.js`).

Contrato que fija esta prueba:
  - `executor.LENGUAJES_SOPORTADOS` incluye "pseint".
  - `executor.LENGUAJES_DE_NAVEGADOR == {"python", "pseint"}`: son los que el
    servidor no ejecuta dentro de un episodio.
  - `RunnerClient.run_pseint(source_code, stdin)` y `docker_runner.run_pseint`.
  - El runner acepta `language: "pseint"`.
  - `settings.pseint_image` (env `PSEINT_IMAGE`), vacio por defecto.
  - Sin imagen, el runner responde 503 `lenguaje_no_disponible`, el cliente
    levanta `LenguajeNoDisponibleError` y la corrida queda con todos los casos
    `skipped` (no es fallo de infraestructura: no corta la correccion).

C07  La correccion corre todos los casos, incluidos los ocultos, sin filtrarlos.
C08  Dentro de un episodio el servidor no ejecuta PSeInt ni emite.
N01  Python y Java siguen igual.
N06  Sin `PSEINT_IMAGE` el runner arranca, Java y Python siguen, la corrida
     PSeInt sale sin ejecutar y el health del runner lo muestra.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from execution_service import runner_main
from execution_service.auth import User
from execution_service.config import settings
from execution_service.routes import executions as ruta
from execution_service.services import docker_runner, executor
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.docker_runner import DockerRunResult
from execution_service.services.executor import run_cases, to_client_payload
from execution_service.services.result_mapper import CaseStatus
from execution_service.services.runner_client import RunnerClient
from fastapi.testclient import TestClient

BANDERAS = [
    "--network=none",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--read-only",
    "--log-driver=none",
]

DOBLE = 'Algoritmo doble\n\tDefinir n Como Entero\n\tLeer n\n\tEscribir n * 2\nFinAlgoritmo\n'


def _tc(i: int, stdin: str, expected: str, publico: bool = True, tipo: str = "stdin_stdout") -> TestCase:
    return TestCase(
        id=f"t{i}",
        name=f"caso {i}",
        type=tipo,
        code=stdin,
        expected=expected,
        is_public=publico,
        weight=1.0,
    )


def _ej(cases: list[TestCase]) -> Ejercicio:
    return Ejercicio(id=uuid4(), language="pseint", inicial_codigo=None, test_cases=cases)


def _ok(stdout: str, code: int = 0) -> DockerRunResult:
    return DockerRunResult(exit_code=code, stdout=stdout, stderr="", timed_out=False, compile_failed=False)


def _imagen(monkeypatch, valor: str) -> None:
    """Fija `settings.pseint_image`. Falla por asercion (no por setup) si falta el campo."""
    assert "pseint_image" in type(settings).model_fields, "falta settings.pseint_image"
    monkeypatch.setattr(settings, "pseint_image", valor)


class _RunnerFalso:
    """Un PSeInt que escribe el doble del stdin."""

    llamadas: list[tuple[str, str]] = []

    def __init__(self, *a, **k) -> None:
        pass

    async def run_pseint(self, source_code: str, stdin: str = "") -> DockerRunResult:
        _RunnerFalso.llamadas.append((source_code, stdin))
        return _ok(f"{int(stdin) * 2}\n")

    async def run_python(self, source_code: str, stdin: str = "") -> DockerRunResult:
        raise AssertionError("un ejercicio PSeInt no puede ir al runner de Python")

    async def run_java(self, source_code: str, stdin: str = "") -> DockerRunResult:
        raise AssertionError("un ejercicio PSeInt no puede ir al runner de Java")


@pytest.fixture
def runner_falso(monkeypatch):
    _RunnerFalso.llamadas = []
    monkeypatch.setattr(executor, "RunnerClient", _RunnerFalso)
    return _RunnerFalso


# ── Contrato ───────────────────────────────────────────────────────────


def test_pseint_es_soportado_y_de_navegador() -> None:
    assert executor.LENGUAJES_SOPORTADOS == frozenset({"java", "python", "pseint"})
    assert executor.LENGUAJES_DE_NAVEGADOR == frozenset({"python", "pseint"})


def test_pseint_image_existe_y_es_vacia_por_defecto() -> None:
    assert "pseint_image" in type(settings).model_fields, "falta settings.pseint_image"
    assert type(settings).model_fields["pseint_image"].default == ""


def test_el_runner_acepta_pseint() -> None:
    req = runner_main.RunRequest(source_code=DOBLE, language="pseint")
    assert req.language == "pseint"
    assert runner_main.RunRequest(source_code="class Main {}").language == "java"
    with pytest.raises(Exception):
        runner_main.RunRequest(source_code="x", language="bash")


async def test_el_cliente_manda_language_pseint(monkeypatch) -> None:
    enviado: dict = {}

    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {"exit_code": 0, "stdout": "42\n", "stderr": "", "timed_out": False, "compile_failed": False}

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
    assert hasattr(RunnerClient, "run_pseint"), "falta RunnerClient.run_pseint"
    r = await RunnerClient(base_url="http://runner", token="t").run_pseint(DOBLE, "21")
    assert enviado["json"]["language"] == "pseint"
    assert enviado["json"]["stdin"] == "21"
    assert r.stdout == "42\n"


# ── C07: docker con las mismas protecciones ────────────────────────────


class _Proc:
    def __init__(self, code: int, out: bytes, capturado: dict) -> None:
        self.returncode = code
        self._out = out
        self._capturado = capturado

    async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
        self._capturado["stdin"] = data.decode()
        return self._out, b""

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.returncode


def _fake_exec(capturado: dict, code: int = 0, out: bytes = b"42\n"):
    async def _fake(*args, **kwargs):
        capturado["args"] = [str(a) for a in args]
        return _Proc(code, out, capturado)

    return _fake


async def test_c07_pseint_corre_con_las_banderas_de_aislamiento(monkeypatch) -> None:
    capturado: dict[str, Any] = {}
    _imagen(monkeypatch, "ghcr.io/x/pseint-sandbox@sha256:" + "c" * 64)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(capturado))
    assert hasattr(docker_runner, "run_pseint"), "falta docker_runner.run_pseint"
    r = await docker_runner.run_pseint(DOBLE, "21")

    args = capturado["args"]
    for bandera in BANDERAS:
        assert bandera in args, bandera
    assert any(a.startswith("--user=") and a != "--user=0" and "root" not in a for a in args)
    assert settings.pseint_image in args
    assert settings.java_image not in args and settings.python_image not in args
    assert capturado["stdin"] == "21"
    assert r.stdout == "42\n"
    assert r.compile_failed is False


async def test_c07_un_error_de_sintaxis_es_no_compila(monkeypatch) -> None:
    capturado: dict[str, Any] = {}
    _imagen(monkeypatch, "ghcr.io/x/pseint-sandbox@sha256:" + "c" * 64)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(capturado, code=101, out=b""))
    r = await docker_runner.run_pseint("Algoritmo roto\n", "")
    assert r.compile_failed is True


# ── C07: correccion con todos los casos ────────────────────────────────


async def test_c07_corre_publicos_y_ocultos(runner_falso) -> None:
    ej = _ej([_tc(0, "3", "6"), _tc(1, "10", "20", publico=False)])
    run = await run_cases(source_code=DOBLE, ejercicio=ej)
    assert [c.status for c in run.cases] == [CaseStatus.PASS, CaseStatus.PASS]
    assert [stdin for _, stdin in runner_falso.llamadas] == ["3", "10"]
    assert (run.total, run.passed, run.failed) == (2, 2, 0)


async def test_c07_los_ocultos_no_filtran(runner_falso) -> None:
    ej = _ej([_tc(0, "3", "6"), _tc(1, "777", "1554", publico=False)])
    run = await run_cases(source_code=DOBLE, ejercicio=ej)
    cable = json.dumps(to_client_payload(run, ej))
    assert "777" not in cable and "1554" not in cable


async def test_c07_un_caso_que_no_es_stdin_stdout_se_saltea(runner_falso) -> None:
    ej = _ej([_tc(0, "3", "6"), _tc(1, "assert algo", "", tipo="pytest_assert")])
    run = await run_cases(source_code=DOBLE, ejercicio=ej)
    assert [c.status for c in run.cases] == [CaseStatus.PASS, CaseStatus.SKIPPED]
    assert [stdin for _, stdin in runner_falso.llamadas] == ["3"]
    assert run.total == 1


# ── C08: dentro de un episodio no se ejecuta ───────────────────────────


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


async def _correr_ruta(monkeypatch, ejercicio: Ejercicio, episode_id: UUID | None, modo: str = "tests") -> None:
    class _Academic:
        async def get_ejercicio(self, ejercicio_id: UUID, tenant_id: UUID) -> Ejercicio:
            return ejercicio

    monkeypatch.setattr(ruta, "AcademicClient", _Academic)
    req = ruta.ExecutionRequest(ejercicio_id=ejercicio.id, source_code=DOBLE, episode_id=episode_id, modo=modo)
    await ruta._run_and_store(uuid4(), req=req, user=_usuario())


async def test_c08_pseint_en_episodio_no_se_ejecuta_ni_emite(monkeypatch, espia, runner_falso) -> None:
    await _correr_ruta(monkeypatch, _ej([_tc(0, "3", "6")]), episode_id=uuid4())
    assert runner_falso.llamadas == [], "el servidor ejecuto PSeInt dentro de un episodio"
    assert espia.emitidos == []


async def test_c08_ejecutar_libre_en_episodio_tampoco(monkeypatch, espia, runner_falso) -> None:
    await _correr_ruta(monkeypatch, _ej([_tc(0, "3", "6")]), episode_id=uuid4(), modo="libre")
    assert runner_falso.llamadas == []
    assert espia.emitidos == []


async def test_c08_sin_episodio_si_se_ejecuta(monkeypatch, espia, runner_falso) -> None:
    await _correr_ruta(monkeypatch, _ej([_tc(0, "3", "6")]), episode_id=None)
    assert [stdin for _, stdin in runner_falso.llamadas] == ["3"]
    assert espia.guardado is not None and espia.guardado["passed"] == 1
    assert espia.emitidos == []


# ── N06: sin imagen, solo PSeInt queda sin ejecutar ────────────────────


def _produccion_ok(monkeypatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "runner_token", "x" * 40)
    monkeypatch.setattr(settings, "java_image", "eclipse-temurin@sha256:" + "a" * 64)
    monkeypatch.setattr(settings, "python_image", "python@sha256:" + "b" * 64)


def test_n06_sin_pseint_image_el_runner_arranca(monkeypatch) -> None:
    _produccion_ok(monkeypatch)
    _imagen(monkeypatch, "")
    assert runner_main.verificar_configuracion_segura() == []


def test_n06_pseint_image_por_tag_en_produccion_no_arranca(monkeypatch) -> None:
    _produccion_ok(monkeypatch)
    _imagen(monkeypatch, "ghcr.io/x/pseint-sandbox:latest")
    assert any("PSEINT_IMAGE" in p for p in runner_main.verificar_configuracion_segura())
    _imagen(monkeypatch, "ghcr.io/x/pseint-sandbox@sha256:" + "c" * 64)
    assert runner_main.verificar_configuracion_segura() == []


def test_n06_el_runner_sin_imagen_responde_lenguaje_no_disponible(monkeypatch) -> None:
    _imagen(monkeypatch, "")
    monkeypatch.setattr(settings, "runner_token", "")
    monkeypatch.setattr(settings, "environment", "development")
    llamado = {"docker": False}

    async def _no_docker(*a, **k):
        llamado["docker"] = True
        raise AssertionError("sin imagen no se lanza docker")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _no_docker)
    with TestClient(runner_main.app) as c:
        r = c.post("/run", json={"source_code": DOBLE, "stdin": "3", "language": "pseint"})
        assert r.status_code == 503
        assert r.json()["detail"] == "lenguaje_no_disponible"
        salud = c.get("/health/live").json()
    assert llamado["docker"] is False
    assert "pseint" not in salud["lenguajes"]
    assert {"java", "python"} <= set(salud["lenguajes"])


async def test_n06_el_cliente_traduce_el_503_a_lenguaje_no_disponible(monkeypatch) -> None:
    from execution_service.services import runner_client as rc

    class _Resp:
        status_code = 503

        def json(self) -> dict:
            return {"detail": "lenguaje_no_disponible"}

    class _Cliente:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url, headers=None, json=None):
            return _Resp()

    monkeypatch.setattr(rc.httpx, "AsyncClient", _Cliente)
    assert hasattr(rc, "LenguajeNoDisponibleError"), "falta runner_client.LenguajeNoDisponibleError"
    with pytest.raises(rc.LenguajeNoDisponibleError):
        await RunnerClient(base_url="http://runner", token="t").run_pseint(DOBLE, "3")


async def test_n06_la_corrida_pseint_sin_imagen_sale_sin_ejecutar(monkeypatch) -> None:
    from execution_service.services import runner_client as rc

    class _SinImagen:
        def __init__(self, *a, **k) -> None:
            pass

        async def run_pseint(self, source_code: str, stdin: str = "") -> DockerRunResult:
            raise rc.LenguajeNoDisponibleError("pseint")

    monkeypatch.setattr(executor, "RunnerClient", _SinImagen)
    ej = _ej([_tc(0, "3", "6"), _tc(1, "10", "20", publico=False)])
    run = await run_cases(source_code=DOBLE, ejercicio=ej)
    assert run.outcome.value == "completed", "no es fallo de infraestructura"
    assert [c.status for c in run.cases] == [CaseStatus.SKIPPED, CaseStatus.SKIPPED]
    assert run.total == 0
