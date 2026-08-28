"""El boton "Ejecutar" de un lenguaje remoto, verificado DONDE se aplica.

En Python el alumno escribe, aprieta "Ejecutar" y ve lo que su programa
imprime. En Java eso no existia: el navegador no tiene runtime, asi que
"Ejecutar" y "Probar" posteaban la MISMA request y el servidor corria los
casos. "Ejecutar" era una corrida de tests con otro nombre — y sobre un
ejercicio sin casos no ejecutaba nada, devolvia una consola vacia, y el
`failed == 0` resultante le daba N4 al labeler.

`modo="libre"` corre el programa una sola vez con el stdin del alumno y
devuelve su salida. La propiedad que este archivo protege es UNA:

    una corrida libre NUNCA emite `tests_ejecutados`

y no es cosmetica. Una corrida libre no evalua nada, asi que su payload
lleva `total=0, passed=0, failed=0`. Si llegara al emisor, el labeler leeria
ese `failed == 0` como "aprobo todo" y etiquetaria N4 el nivel mas alto del
modelo sobre un episodio donde no se evaluo una sola linea. Es exactamente el
agujero que `should_emit` cerro por el otro lado el 2026-08-28, entrando por
la puerta nueva.

Hay DOS barreras y las dos se prueban acá, porque cada una tapa un descuido
distinto:

  1. el `req.modo != "libre"` del `if` de la ruta
  2. el tipo: `run_libre` devuelve `CorridaLibre`, no `RunResult`, asi que
     `run` queda en None y no hay conteos que filtrar aunque alguien toque (1)

Y la contracara, que es la que impide el "arreglo" barato: el alumno TIENE
que ver su salida. Cortar antes de correr tambien pasa los tests de arriba.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from execution_service.auth import User
from execution_service.routes import executions as ruta
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.executor import CorridaLibre

EPISODIO = UUID("e9150d10-0000-0000-0000-000000000002")

HOLA = """\
public class Main {
    public static void main(String[] a) { System.out.println("hola"); }
}
"""


def _usuario() -> User:
    return User(
        id=uuid4(),
        tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alumno@utn.edu.ar",
        roles=frozenset({"estudiante"}),
    )


def _ejercicio(*, language: str = "java", con_casos: bool = False) -> Ejercicio:
    casos = (
        [
            TestCase(
                id="c1",
                name="caso 1",
                type="stdin_stdout",
                code="",
                expected="hola",
                is_public=True,
                weight=1.0,
            )
        ]
        if con_casos
        else []
    )
    return Ejercicio(
        id=uuid4(), language=language, inicial_codigo="public class Main {}", test_cases=casos
    )


class _Espia:
    def __init__(self) -> None:
        self.emitidos: list[dict[str, Any]] = []
        self.guardado: dict[str, Any] | None = None
        self.stdin_recibido: str | None = None
        self.corridas = 0


@pytest.fixture
def espia(monkeypatch: pytest.MonkeyPatch) -> _Espia:
    """Aisla la ruta del store y del tutor. El sandbox se dobla por test."""
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


async def _correr(
    monkeypatch: pytest.MonkeyPatch,
    espia: _Espia,
    *,
    ejercicio: Ejercicio,
    modo: str = "libre",
    stdin: str = "",
    salida: str = "hola\n",
    stderr: str = "",
    compile_failed: bool = False,
) -> None:
    monkeypatch.setattr(ruta, "AcademicClient", _academic(ejercicio))

    async def _libre(*, source_code: str, language: str, stdin: str = "") -> CorridaLibre:
        espia.corridas += 1
        espia.stdin_recibido = stdin
        return CorridaLibre(
            stdout=salida,
            stderr=stderr,
            exit_code=1 if compile_failed else 0,
            timed_out=False,
            compile_failed=compile_failed,
            ejecutado=True,
        )

    monkeypatch.setattr(ruta, "run_libre", _libre)
    req = ruta.ExecutionRequest(
        ejercicio_id=ejercicio.id,
        source_code=HOLA,
        episode_id=EPISODIO,
        modo=modo,
        stdin=stdin,
    )
    await ruta._run_and_store(uuid4(), req=req, user=_usuario())


# ── La propiedad ───────────────────────────────────────────────────────────


async def test_la_corrida_libre_NO_emite_tests_ejecutados(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """Con episodio presente y todo lo demas en su lugar: igual no emite."""
    await _correr(monkeypatch, espia, ejercicio=_ejercicio())
    assert espia.emitidos == [], f"la corrida libre emitio un evento de conteos: {espia.emitidos}"


async def test_tampoco_emite_cuando_el_ejercicio_SI_tiene_casos(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """El modo manda, no los datos.

    Sin este test, "no emite porque no hay casos" pasaria por "no emite porque
    es libre" — y son dos razones distintas. Un ejercicio con casos corrido en
    modo libre tampoco evaluo nada.
    """
    await _correr(monkeypatch, espia, ejercicio=_ejercicio(con_casos=True))
    assert espia.emitidos == []


async def test_el_modo_tests_SIGUE_emitiendo(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """La otra mitad: apagar la emision para todo tambien pasa los de arriba.

    Este es el que impide que el candado se convierta en un apagon.
    """
    ejercicio = _ejercicio(con_casos=True)
    monkeypatch.setattr(ruta, "AcademicClient", _academic(ejercicio))

    from execution_service.services.result_mapper import (
        CaseResult,
        CaseStatus,
        RunOutcome,
        RunResult,
    )

    async def _run_cases(*, source_code: str, ejercicio: Ejercicio) -> RunResult:
        return RunResult(
            outcome=RunOutcome.COMPLETED,
            cases=[
                CaseResult(
                    id="c1",
                    name="caso 1",
                    type="stdin_stdout",
                    status=CaseStatus.PASS,
                    input="",
                    expected="hola",
                    got="hola",
                    error=None,
                    weight=1.0,
                )
            ],
        )

    monkeypatch.setattr(ruta, "run_cases", _run_cases)
    req = ruta.ExecutionRequest(
        ejercicio_id=ejercicio.id, source_code=HOLA, episode_id=EPISODIO, modo="tests"
    )
    await ruta._run_and_store(uuid4(), req=req, user=_usuario())
    assert len(espia.emitidos) == 1, "el modo tests dejo de emitir: el candado se paso de rosca"


# ── Y el alumno ve su salida ───────────────────────────────────────────────


async def test_el_alumno_ve_lo_que_imprimio_su_programa(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """Cortar antes de correr tambien pasa los tests de arriba. Esto lo impide."""
    await _correr(monkeypatch, espia, ejercicio=_ejercicio(), salida="hola mundo\n")
    assert espia.corridas == 1, "no se ejecuto el programa"
    assert espia.guardado is not None
    assert espia.guardado["stdout"] == "hola mundo\n"
    assert espia.guardado["modo"] == "libre"


async def test_el_stdin_del_alumno_llega_al_sandbox(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """La entrada viaja entera y por adelantado: no hay `input()` interactivo."""
    await _correr(monkeypatch, espia, ejercicio=_ejercicio(), stdin="42\nJuani\n")
    assert espia.stdin_recibido == "42\nJuani\n"


async def test_un_error_de_compilacion_se_ve_donde_el_cliente_lo_busca(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """El caso en que MAS necesita verlo: corrio libre justamente para probar."""
    await _correr(
        monkeypatch,
        espia,
        ejercicio=_ejercicio(),
        salida="",
        stderr="Main.java:2: error: ';' expected",
        compile_failed=True,
    )
    assert espia.guardado is not None
    assert "';' expected" in espia.guardado["compile_output"]
    assert espia.emitidos == [], "una compilacion fallida en libre tampoco emite"


async def test_los_conteos_del_payload_libre_van_en_cero(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """No porque haya fallado: porque no se evaluo nada. Lo dice `modo`."""
    await _correr(monkeypatch, espia, ejercicio=_ejercicio(con_casos=True))
    assert espia.guardado is not None
    assert (espia.guardado["total"], espia.guardado["passed"], espia.guardado["failed"]) == (
        0,
        0,
        0,
    )
    assert espia.guardado["cases"] == []


# ── La segunda barrera, probada donde SI se puede ─────────────────────────
#
# Los seis tests de arriba pasan IGUAL si se saca el `modo != "libre"` del
# predicado. Verificado con el mutante el 2026-08-28: 7 en verde sin el
# candado. No es que sobre — es que hoy lo tapa el `run is not None`, porque en
# modo libre `run` nunca se setea.
#
# O sea que la propiedad se sostiene sobre un detalle de implementacion y no
# sobre una decision. El dia que alguien haga que la rama libre escriba `run`
# —por ejemplo para reusar `to_client_payload`— esa barrera desaparece sin que
# nadie lo note.
#
# Desde dentro de `_run_and_store` eso NO se puede probar: `run` es una
# variable local y ningun monkeypatch la alcanza. Por eso la decision se
# extrajo a `debe_emitir_conteos`, que se llama con los cuatro terminos
# explicitos. Acá se prueba cada uno por separado, incluido el estado futuro
# que hoy no existe.


def _run_con_un_caso():
    from execution_service.services.result_mapper import (
        CaseResult,
        CaseStatus,
        RunOutcome,
        RunResult,
    )

    return RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            CaseResult(
                id="c1",
                name="caso 1",
                type="stdin_stdout",
                status=CaseStatus.PASS,
                input="",
                expected="hola",
                got="hola",
                error=None,
                weight=1.0,
            )
        ],
    )


def test_el_modo_libre_no_emite_NI_CON_run_seteado() -> None:
    """El estado post-refactor: `run` con conteos reales y modo libre.

    Si este test se pone rojo y los otros siguen verdes, alguien saco el
    `modo != "libre"` creyendolo redundante. Es lo unico que queda cuando
    `run` deja de ser `None`.
    """
    assert not ruta.debe_emitir_conteos(
        modo="libre",
        episode_id=EPISODIO,
        run=_run_con_un_caso(),
        ejercicio=_ejercicio(con_casos=True),
    )


def test_el_modo_tests_con_todo_en_su_lugar_SI_emite() -> None:
    """La contracara: sin esto, `return False` pelado pasa el de arriba."""
    assert ruta.debe_emitir_conteos(
        modo="tests",
        episode_id=EPISODIO,
        run=_run_con_un_caso(),
        ejercicio=_ejercicio(con_casos=True),
    )


def test_sin_episodio_no_emite_aunque_sea_modo_tests() -> None:
    """El panel del docente: corre fuera de todo episodio."""
    assert not ruta.debe_emitir_conteos(
        modo="tests",
        episode_id=None,
        run=_run_con_un_caso(),
        ejercicio=_ejercicio(con_casos=True),
    )


def test_sin_run_no_emite() -> None:
    assert not ruta.debe_emitir_conteos(
        modo="tests", episode_id=EPISODIO, run=None, ejercicio=_ejercicio()
    )


def test_una_corrida_vacia_en_modo_tests_tampoco_emite() -> None:
    """El guard anti-inflacion original sigue adentro del predicado."""
    from execution_service.services.result_mapper import RunOutcome, RunResult

    assert not ruta.debe_emitir_conteos(
        modo="tests",
        episode_id=EPISODIO,
        run=RunResult(outcome=RunOutcome.COMPLETED, cases=[]),
        ejercicio=_ejercicio(),
    )
