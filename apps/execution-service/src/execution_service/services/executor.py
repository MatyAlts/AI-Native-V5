"""Orquestacion de una corrida: casos publicos + ocultos, y la frontera de salida.

Este modulo tiene DOS responsabilidades y conviene no mezclarlas al leerlo:

1. `run_cases` — ejecuta TODOS los casos del ejercicio, publicos y ocultos.
2. `to_client_payload` — decide que de eso sale hacia el navegador.

La segunda es la que importa para la seguridad. El servicio lee los casos
ocultos con un rol privilegiado; **si esa informacion se filtrara en la
respuesta, la evaluacion honesta se rompe y el privilegio se vuelve una fuga.**

Que se le dice al alumno sobre un caso oculto: solo que existe y si paso. NO su
nombre, NO su codigo, NO la salida esperada, NO lo que su programa imprimio
(que revelaria el caso por diferencia). El test de la tarea 3.5 lo verifica
sobre el payload serializado, no sobre la estructura interna.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.docker_runner import to_sandbox_result
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
    infrastructure_failure,
    map_case,
)
from execution_service.services.runner_client import LenguajeNoDisponibleError, RunnerClient
from execution_service.services.sandbox_types import SandboxUnavailableError

# Lenguajes que este servicio sabe ejecutar server-side. Agregar uno es una
# imagen y un comando en `docker_runner`.
#
# Python esta desde HU-015, y SOLO por la correccion con IA: sin el resultado
# real de cada caso, el motor leia "fallo todo" sobre codigo correcto. El
# "Probar" del alumno en Python sigue en el navegador con Pyodide (ADR-033),
# que es instantaneo y gratis: el web-student no llama a este servicio para
# Python.
#
# PSeInt esta desde HU-030 (ADR-064) con el mismo criterio que Python: el
# alumno ejecuta y prueba en el navegador con el interprete de
# `packages/pseint`, y el servidor corre el mismo interprete solo para la
# correccion con IA. Su imagen es opcional (N06): sin `PSEINT_IMAGE` la
# corrida sale con todos los casos `skipped`.
LENGUAJES_SOPORTADOS: frozenset[str] = frozenset({"java", "python", "pseint"})

# Lenguajes que el alumno corre en el NAVEGADOR. Dentro de un episodio el
# servidor no los ejecuta ni emite `tests_ejecutados` (HU-015 C11, HU-030 C08):
# el evento que vale es el del navegador.
LENGUAJES_DE_NAVEGADOR: frozenset[str] = frozenset({"python", "pseint"})

# Metodo del `RunnerClient` por lenguaje. Se resuelve con `getattr` recien al
# correr, para que un doble que solo implementa un lenguaje siga sirviendo.
_METODO_DEL_RUNNER: dict[str, str] = {
    "java": "run_java",
    "python": "run_python",
    "pseint": "run_pseint",
}

# Rotulo generico de un caso oculto. El numero es su posicion entre los ocultos,
# no su id ni su nombre real: el alumno puede contar cuantos hay sin saber que
# prueban.
HIDDEN_CASE_LABEL = "Caso oculto"


async def run_cases(
    *,
    source_code: str,
    ejercicio: Ejercicio,
) -> RunResult:
    """Corre el codigo contra todos los casos del ejercicio.

    Un fallo del sandbox devuelve `INFRASTRUCTURE_FAILURE` con la lista de casos
    VACIA — nunca casos fallidos (D4). Es la propiedad que protege el corpus.
    """
    if ejercicio.language not in LENGUAJES_SOPORTADOS:
        # Un lenguaje sin runtime no es un fallo de infraestructura ni del
        # alumno: no hay donde ejecutarlo. Todos los casos quedan `skipped`.
        return RunResult(
            outcome=RunOutcome.COMPLETED,
            cases=[_skipped(tc, i) for i, tc in enumerate(ejercicio.test_cases)],
        )

    cases: list[CaseResult] = []
    correr = getattr(RunnerClient(), _METODO_DEL_RUNNER[ejercicio.language])

    try:
        for i, tc in enumerate(ejercicio.test_cases):
            if ejercicio.language in LENGUAJES_DE_NAVEGADOR and tc.type != "stdin_stdout":
                # HU-015, C09. Un `pytest_assert` es codigo de prueba, no una
                # entrada: mandarlo como stdin no lo ejecuta, y con `expected`
                # nulo cualquier programa que termine bien lo "aprobaba". No
                # hay como correrlo de verdad server-side, asi que queda
                # `skipped` (la correccion lo muestra como no ejecutado) y no
                # cuenta en `total`. Java no pasa por aca; PSeInt solo tiene
                # casos de entrada y salida (HU-030).
                cases.append(_skipped(tc, i, motivo=_MOTIVO_TIPO_NO_EJECUTABLE))
                continue
            stdin = tc.code if tc.type == "stdin_stdout" else ""
            crudo = await correr(source_code, stdin)
            result = to_sandbox_result(crudo, tc.expected)
            cases.append(
                map_case(
                    case_id=tc.id,
                    name=tc.name,
                    case_type=tc.type,
                    stdin=stdin,
                    expected=tc.expected,
                    weight=tc.weight,
                    result=result,
                )
            )
    except LenguajeNoDisponibleError:
        # HU-030, N06. Sin imagen de PSeInt en el runner no es un fallo de
        # infraestructura: la correccion sigue, con todos los casos "sin
        # ejecutar" (como un lenguaje sin runtime).
        return RunResult(
            outcome=RunOutcome.COMPLETED,
            cases=[
                _skipped(tc, i, motivo=_MOTIVO_LENGUAJE_NO_DISPONIBLE)
                for i, tc in enumerate(ejercicio.test_cases)
            ],
        )
    except (SandboxUnavailableError, OSError) as exc:
        # Se descarta lo parcial a proposito: media corrida no es un resultado.
        return infrastructure_failure(str(exc))

    return RunResult(outcome=RunOutcome.COMPLETED, cases=cases)


@dataclass(frozen=True)
class CorridaLibre:
    """Resultado de correr el codigo del alumno SIN casos de prueba.

    Deliberadamente NO es un `RunResult`. Un `RunResult` lleva `total`,
    `passed` y `failed`, y esos tres numeros son de los que el labeler v1.2.0
    deriva N3 vs N4. Una corrida libre no tiene nada que contar: reusar el tipo
    invitaria a alguien a pasarla por `should_emit` y a emitir un
    `tests_ejecutados` con `failed=0` — que es exactamente el N4 falso que el
    guard de la corrida vacia cerro el 2026-08-28.

    El tipo distinto es la barrera: no hay forma de confundirlos.
    """

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    compile_failed: bool
    ejecutado: bool
    """`False` cuando no hay runtime para el lenguaje: no es un fallo del alumno."""


async def run_libre(*, source_code: str, language: str, stdin: str = "") -> CorridaLibre:
    """Compila y corre el codigo una sola vez, con el stdin que mando el alumno.

    Es la contraparte de `run_cases` para el boton "Ejecutar" de un lenguaje
    remoto. Hasta el 2026-08-28 ese boton POSTEABA a `/executions` igual que
    "Probar": en Java las dos acciones eran la MISMA llamada, porque el
    navegador no tiene runtime de Java y la unica corrida posible era contra
    los casos. Con un ejercicio sin casos eso no ejecutaba nada y devolvia
    `total=0, passed=0, failed=0` — una consola vacia para el alumno y un N4
    para el labeler.

    Acá la corrida es de verdad y no produce conteos, asi que las dos mitades
    del problema desaparecen: el alumno ve su salida, y no hay nada que el
    labeler pueda malinterpretar.

    El stdin viaja completo y por adelantado, no interactivo. En Python el
    `input()` se intercepta en el navegador y se le pregunta al alumno en el
    momento; en un contenedor efimero eso no existe: el proceso corre hasta
    terminar sin canal de vuelta.
    """
    if language not in LENGUAJES_SOPORTADOS:
        return CorridaLibre(
            stdout="",
            stderr="No hay entorno de ejecucion para este lenguaje.",
            exit_code=0,
            timed_out=False,
            compile_failed=False,
            ejecutado=False,
        )

    # Desde HU-015 Python tambien esta en `LENGUAJES_SOPORTADOS` (y PSeInt
    # desde HU-030): sin este despacho, un Ejecutar de Python le mandaria el
    # fuente al comando de Java.
    correr = getattr(RunnerClient(), _METODO_DEL_RUNNER[language])
    try:
        crudo = await correr(source_code, stdin)
    except LenguajeNoDisponibleError:
        return CorridaLibre(
            stdout="",
            stderr=_MOTIVO_LENGUAJE_NO_DISPONIBLE,
            exit_code=0,
            timed_out=False,
            compile_failed=False,
            ejecutado=False,
        )
    return CorridaLibre(
        stdout=crudo.stdout,
        stderr=crudo.stderr,
        exit_code=crudo.exit_code,
        timed_out=crudo.timed_out,
        compile_failed=crudo.compile_failed,
        ejecutado=True,
    )


_MOTIVO_SIN_RUNTIME = "No hay entorno de ejecucion para este lenguaje."
_MOTIVO_TIPO_NO_EJECUTABLE = "Este tipo de caso no se ejecuta en el servidor."
_MOTIVO_EPISODIO = (
    "Este lenguaje se ejecuta en el navegador: dentro de un episodio el servidor no lo corre."
)
_MOTIVO_LENGUAJE_NO_DISPONIBLE = (
    "El servidor no tiene el entorno de este lenguaje instalado: el caso queda sin ejecutar."
)


def sin_ejecutar(ejercicio: Ejercicio) -> RunResult:
    """Todos los casos `skipped`, sin llamar al runner (HU-015, C11).

    Es la respuesta para un lenguaje de navegador (`LENGUAJES_DE_NAVEGADOR`:
    Python y PSeInt) dentro de un episodio: el Probar del alumno corre en el
    navegador y el servidor no ejecuta nada. Es la misma forma que
    devolvia el servicio antes de HU-015 (Python sin runtime), asi que el
    cliente ya la entiende como "sin ejecutar" y no como fallo de
    infraestructura. `total == 0`, y `should_emit` no la deja emitir.
    """
    return RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _skipped(tc, i, motivo=_MOTIVO_EPISODIO) for i, tc in enumerate(ejercicio.test_cases)
        ],
    )


def _skipped(tc: TestCase, index: int, *, motivo: str = _MOTIVO_SIN_RUNTIME) -> CaseResult:
    return CaseResult(
        id=tc.id,
        name=tc.name,
        type=tc.type,
        status=CaseStatus.SKIPPED,
        input="",
        expected=None,
        got="",
        error=motivo,
        weight=tc.weight,
    )


def to_client_payload(run: RunResult, ejercicio: Ejercicio) -> dict[str, Any]:
    """Serializa el resultado para el NAVEGADOR, sin filtrar casos ocultos.

    Es la frontera de seguridad del servicio. Todo lo que salga de acá lo puede
    leer el alumno abriendo las herramientas de desarrollo.
    """
    hidden_ids = {tc.id for tc in ejercicio.hidden_cases}

    cases: list[dict[str, Any]] = []
    hidden_seen = 0
    for case in run.cases:
        if case.id in hidden_ids:
            hidden_seen += 1
            cases.append(
                {
                    # El id se reemplaza: el real puede aparecer en la rubrica
                    # o en el JSON de importacion del docente.
                    "id": f"hidden-{hidden_seen}",
                    "name": f"{HIDDEN_CASE_LABEL} {hidden_seen}",
                    "type": case.type,
                    "status": case.status.value,
                    "is_public": False,
                    # Sin input, sin expected, sin got: cualquiera de los tres
                    # permite reconstruir que prueba el caso.
                    "input": None,
                    "expected": None,
                    "got": None,
                    # El error tambien se omite: una traza puede contener el
                    # valor esperado o el nombre del metodo evaluado.
                    "error": None,
                    "weight": case.weight,
                }
            )
        else:
            cases.append(
                {
                    "id": case.id,
                    "name": case.name,
                    "type": case.type,
                    "status": case.status.value,
                    "is_public": True,
                    "input": case.input,
                    "expected": case.expected,
                    "got": case.got,
                    "error": case.error,
                    "weight": case.weight,
                }
            )

    return {
        "outcome": run.outcome.value,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "cases": cases,
        # `compile_output` sale SOLO si el codigo del alumno no compilo: es su
        # propio error y lo necesita para arreglarlo. Ante fallo de
        # infraestructura lleva el motivo interno, que no se le muestra.
        "compile_output": (
            run.compile_output if run.outcome is RunOutcome.COMPILATION_ERROR else ""
        ),
    }
