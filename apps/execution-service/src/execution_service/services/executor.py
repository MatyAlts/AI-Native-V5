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

from typing import Any

from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.judge0_client import Judge0Client, Judge0UnavailableError
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
    infrastructure_failure,
    map_case,
)

# Judge0 language ids. Java 62 = OpenJDK 13.0.1, el id estable del catalogo.
LANGUAGE_IDS: dict[str, int] = {"java": 62}

# Rotulo generico de un caso oculto. El numero es su posicion entre los ocultos,
# no su id ni su nombre real: el alumno puede contar cuantos hay sin saber que
# prueban.
HIDDEN_CASE_LABEL = "Caso oculto"


async def run_cases(
    *,
    source_code: str,
    ejercicio: Ejercicio,
    client: Judge0Client | None = None,
) -> RunResult:
    """Corre el codigo contra todos los casos del ejercicio.

    Un fallo del sandbox devuelve `INFRASTRUCTURE_FAILURE` con la lista de casos
    VACIA — nunca casos fallidos (D4). Es la propiedad que protege el corpus.
    """
    language_id = LANGUAGE_IDS.get(ejercicio.language)
    if language_id is None:
        # Un lenguaje sin runtime no es un fallo de infraestructura ni del
        # alumno: no hay donde ejecutarlo. Todos los casos quedan `skipped`.
        return RunResult(
            outcome=RunOutcome.COMPLETED,
            cases=[_skipped(tc, i) for i, tc in enumerate(ejercicio.test_cases)],
        )

    judge0 = client or Judge0Client()
    cases: list[CaseResult] = []

    try:
        for tc in ejercicio.test_cases:
            token = await judge0.submit(
                source_code=source_code,
                language_id=language_id,
                stdin=tc.code if tc.type == "stdin_stdout" else "",
                expected_output=tc.expected,
            )
            result = await judge0.get_result(token)
            cases.append(
                map_case(
                    case_id=tc.id,
                    name=tc.name,
                    case_type=tc.type,
                    stdin=tc.code if tc.type == "stdin_stdout" else "",
                    expected=tc.expected,
                    weight=tc.weight,
                    result=result,
                )
            )
    except Judge0UnavailableError as exc:
        # Se descarta lo parcial a proposito: media corrida no es un resultado.
        return infrastructure_failure(str(exc))

    return RunResult(outcome=RunOutcome.COMPLETED, cases=cases)


def _skipped(tc: TestCase, index: int) -> CaseResult:
    return CaseResult(
        id=tc.id,
        name=tc.name,
        type=tc.type,
        status=CaseStatus.SKIPPED,
        input="",
        expected=None,
        got="",
        error="No hay entorno de ejecucion para este lenguaje.",
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
