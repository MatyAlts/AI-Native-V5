"""Tests de la emision del evento de trazabilidad (tareas 5.3 y 5.5).

El test central es `test_un_fallo_de_infraestructura_no_emite_evento`. Protege
el corpus de la tesis por un camino que las tareas de la change no anticipaban:
no alcanza con que un fallo de infra reporte 0 fallidos, porque el etiquetador
lee justamente ese 0 como "paso todo".
"""

from __future__ import annotations

from uuid import uuid4

from execution_service.services.ctr_emitter import (
    build_payload,
    idempotency_key,
    should_emit,
)
from execution_service.services.result_mapper import (
    RunOutcome,
    RunResult,
    infrastructure_failure,
    map_case,
)
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus


def _caso(case_id: str, status: SandboxStatus):
    return map_case(
        case_id=case_id,
        name=f"caso {case_id}",
        case_type="stdin_stdout",
        stdin="",
        expected="ok",
        weight=1.0,
        result=SandboxResult(
            status=status,
            stdout="ok",
            stderr="",
            compile_output="",
            time_seconds=0.2,
            memory_kb=1000,
        ),
    )


# ── La regla que protege el corpus ─────────────────────────────────────────


def test_un_fallo_de_infraestructura_no_emite_evento() -> None:
    """**No cambiar a "emitir igual" sin leer esto.**

    El etiquetador N1-N4 (`event_labeler`, regla de `tests_ejecutados` v1.2.0)
    hace:

        failed > 0                         -> N3
        failed == 0 y tutor lejano (>=60s) -> N4 (apropiacion reflexiva)

    D4 hace que un fallo de infraestructura reporte `failed = 0` para que NO se
    registre como el alumno fallando todo. Pero si ademas se emitiera el evento,
    ese 0 caeria en la segunda rama: **un sandbox caido etiquetaria el episodio
    como apropiacion reflexiva**, el nivel mas alto del modelo de la tesis.

    No degrada la clasificacion: la INFLA. Es peor que el problema original.

    Se resuelve no emitiendo. El evento se llama `tests_ejecutados`; si no se
    ejecutaron, no hay evento.
    """
    run = infrastructure_failure("sandbox no alcanzable")
    assert should_emit(run) is False


def test_una_corrida_real_si_emite() -> None:
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso("t1", SandboxStatus.ACCEPTED)],
    )
    assert should_emit(run) is True


def test_una_corrida_con_fallos_tambien_emite() -> None:
    """Fallar tests es informacion pedagogica valida: se registra."""
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso("t1", SandboxStatus.WRONG_ANSWER)],
    )
    assert should_emit(run) is True


# ── Conteo de ocultos ──────────────────────────────────────────────────────


def test_los_ocultos_ejecutados_se_cuentan_de_verdad() -> None:
    """`tests_hidden` deja de ser 0.

    El contrato lo declaraba "siempre 0 en piloto-1 ... reservado para piloto-2
    cuando se implemente sandbox-service". Este es ese servicio.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _caso("publico", SandboxStatus.ACCEPTED),
            _caso("oculto-1", SandboxStatus.ACCEPTED),
            _caso("oculto-2", SandboxStatus.WRONG_ANSWER),
        ],
    )
    payload = build_payload(
        run,
        hidden_case_ids={"oculto-1", "oculto-2"},
        ejecucion_ms=1200,
        engine="judge0",
    )

    assert payload["test_count_total"] == 3
    assert payload["tests_hidden"] == 2
    assert payload["tests_publicos"] == 1
    assert payload["test_count_passed"] == 2
    assert payload["test_count_failed"] == 1


def test_el_payload_declara_el_motor_real() -> None:
    """Tarea 5.1 — el evento deja de declarar un entorno fijo."""
    run = RunResult(outcome=RunOutcome.COMPLETED, cases=[_caso("t1", SandboxStatus.ACCEPTED)])
    payload = build_payload(run, hidden_case_ids=set(), ejecucion_ms=500, engine="judge0")
    assert payload["execution_engine"] == "judge0"


# ── Idempotencia (tarea 5.5) ───────────────────────────────────────────────


def test_la_clave_de_idempotencia_es_estable_para_la_misma_ejecucion() -> None:
    """Un reintento NO agrega un segundo evento a la cadena.

    Con ejecucion en el navegador, perder un evento era gratis. Con ejecucion
    server-side la corrida ya se pago en computo, dinero y cuota del alumno: si
    el evento se pierde, para el clasificador esa ejecucion nunca existio. Y si
    se duplica, contamina el conteo.
    """
    execution_id = uuid4()
    assert idempotency_key(execution_id) == idempotency_key(execution_id)


def test_ejecuciones_distintas_tienen_claves_distintas() -> None:
    assert idempotency_key(uuid4()) != idempotency_key(uuid4())
