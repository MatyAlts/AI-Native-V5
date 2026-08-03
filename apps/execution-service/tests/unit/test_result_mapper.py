"""Tests de la traduccion sandbox → formato de casos del sistema.

El test que mas importa de este archivo es
`test_fallo_de_infraestructura_no_produce_casos_fallidos`: protege el corpus de
la tesis. Ver D4 del design de `java-execution-engine`.
"""

from __future__ import annotations

import pytest
from execution_service.services.result_mapper import (
    CaseStatus,
    RunOutcome,
    RunResult,
    infrastructure_failure,
    map_case,
)
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus


def _result(
    status: SandboxStatus, *, stdout: str = "", stderr: str = "", compile_output: str = ""
) -> SandboxResult:
    return SandboxResult(
        status=status,
        stdout=stdout,
        stderr=stderr,
        compile_output=compile_output,
        time_seconds=0.4,
        memory_kb=14000,
    )


def _case(result: SandboxResult):
    return map_case(
        case_id="t1",
        name="caso basico",
        case_type="stdin_stdout",
        stdin="",
        expected="Hola",
        weight=1.0,
        result=result,
    )


def test_accepted_es_pass() -> None:
    assert _case(_result(SandboxStatus.ACCEPTED, stdout="Hola\n")).status is CaseStatus.PASS


def test_wrong_answer_es_fail() -> None:
    caso = _case(_result(SandboxStatus.WRONG_ANSWER, stdout="Chau\n"))
    assert caso.status is CaseStatus.FAIL
    assert caso.got == "Chau\n"
    # Un fail NO lleva mensaje de error: el alumno fallo el caso, no hubo fallo.
    assert caso.error is None


def test_error_de_compilacion_lleva_el_mensaje_del_compilador() -> None:
    caso = _case(_result(SandboxStatus.COMPILATION_ERROR, compile_output="error: ';' expected\n"))
    assert caso.status is CaseStatus.ERROR
    assert caso.error is not None
    assert "';' expected" in caso.error


def test_timeout_explica_el_bucle_infinito() -> None:
    """El alumno tiene que entender QUE paso, no ver un codigo de estado."""
    caso = _case(_result(SandboxStatus.TIME_LIMIT_EXCEEDED))
    assert caso.status is CaseStatus.ERROR
    assert caso.error is not None
    assert "tiempo limite" in caso.error
    assert "bucle infinito" in caso.error


@pytest.mark.parametrize(
    "status",
    [
        SandboxStatus.RUNTIME_ERROR_SIGSEGV,
        SandboxStatus.RUNTIME_ERROR_SIGFPE,
        SandboxStatus.RUNTIME_ERROR_NZEC,
        SandboxStatus.RUNTIME_ERROR_OTHER,
    ],
)
def test_errores_de_runtime_son_error_y_nunca_fail(status: SandboxStatus) -> None:
    """Un crash NO es "el alumno fallo el caso".

    Si se mapeara a `fail`, el conteo de fallidos que consume el clasificador
    incluiria crashes, que son otra cosa pedagogicamente.
    """
    assert _case(_result(status)).status is CaseStatus.ERROR


def test_status_desconocido_degrada_a_error_no_a_pass() -> None:
    """Ante un status que no conocemos, el default seguro es error.

    Si Judge0 agrega un status nuevo, preferimos marcar error antes que dar por
    bueno un caso que no sabemos si paso.
    """
    assert _case(_result(SandboxStatus.INTERNAL_ERROR)).status is CaseStatus.ERROR


# ── El test que protege el corpus ──────────────────────────────────────────


def test_fallo_de_infraestructura_no_produce_casos_fallidos() -> None:
    """D4 — tarea 5.3. **No borrar sin leer esto.**

    El clasificador usa `test_count_failed` para separar apropiacion reflexiva
    de superficial. Si una caida del sandbox se registrara como el alumno
    fallando todos los casos, un problema de red degradaria la clasificacion
    pedagogica de un episodio real del piloto — datos de la tesis contaminados
    por un fallo de infraestructura.
    """
    run = infrastructure_failure("sandbox no alcanzable: ConnectError")

    assert run.outcome is RunOutcome.INFRASTRUCTURE_FAILURE
    assert run.failed == 0, "un fallo de infra NUNCA cuenta como casos fallidos"
    assert run.total == 0, "no corrio ningun caso"
    assert run.passed == 0
    assert run.cases == [], "no se inventan casos que nunca se ejecutaron"


def test_una_corrida_real_con_fallos_si_los_cuenta() -> None:
    """El contraste del anterior: cuando SI corrieron, el conteo es real."""
    cases = [
        _case(_result(SandboxStatus.ACCEPTED, stdout="Hola\n")),
        _case(_result(SandboxStatus.WRONG_ANSWER, stdout="Chau\n")),
        _case(_result(SandboxStatus.WRONG_ANSWER, stdout="")),
    ]
    run = RunResult(outcome=RunOutcome.COMPLETED, cases=cases)

    assert run.total == 3
    assert run.passed == 1
    assert run.failed == 2


def test_los_casos_skipped_no_entran_en_el_total() -> None:
    """Un caso que no se ejecuto no aprobo ni reprobo.

    Mismo criterio que el panel del docente adopto en la epic anterior.
    """
    from execution_service.services.result_mapper import CaseResult

    cases = [
        _case(_result(SandboxStatus.ACCEPTED, stdout="Hola\n")),
        CaseResult(
            id="t2",
            name="caso sin runtime",
            type="junit_assert",
            status=CaseStatus.SKIPPED,
            input="",
            expected=None,
            got="",
            error="No se ejecuto.",
            weight=1.0,
        ),
    ]
    run = RunResult(outcome=RunOutcome.COMPLETED, cases=cases)

    assert run.total == 1, "el skipped no cuenta como caso corrido"
    assert run.passed == 1
    assert run.failed == 0
