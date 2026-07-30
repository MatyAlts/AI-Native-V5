"""Una corrida SIN casos aprobados no puede etiquetarse como apropiacion reflexiva.

Estos tests cierran el flanco que `ctr_emitter.py` deja abierto. Su docstring
razona el problema bien y lo resuelve para UN camino:

    failed == 0 y tutor lejano (>=60s)  -> N4  (apropiacion reflexiva)

    "Con `failed = 0` por fallo de infraestructura, un sandbox caido caeria en
     la segunda rama: el episodio quedaria etiquetado como apropiacion
     reflexiva, el nivel mas alto del modelo de la tesis, porque el servidor se
     rompio. Es peor que el problema que D4 evita: no degrada la
     clasificacion, la infla."

Cierra ese camino no emitiendo evento ante `INFRASTRUCTURE_FAILURE`. Correcto.

Pero `failed == 0` tiene OTRA puerta de entrada, y esa quedo abierta:
`RunResult.failed` cuenta unicamente `CaseStatus.FAIL`. Un caso en
`CaseStatus.ERROR` — que es donde `result_mapper` manda al error de
compilacion, al timeout y a todos los crashes de runtime — no suma a `failed`
y tampoco a `passed`. Y `run_cases` devuelve esas corridas con outcome
`COMPLETED`, asi que `should_emit()` da True.

Resultado: el codigo del alumno no compila, se emite `tests_ejecutados` con
`test_count_failed = 0`, y el etiquetador lo lee como que paso todo. Codigo que
ni compila queda registrado en el corpus de la tesis como el nivel mas alto de
apropiacion. Es exactamente la inflacion que el modulo dice evitar, por la
puerta de al lado.

El test que lo prueba de punta a punta es
`test_una_corrida_sin_un_solo_caso_aprobado_no_puede_ser_n4`: corre el
etiquetador REAL del classifier-service sobre el payload REAL del emisor. No
hay dobles en el medio.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from classifier_service.services.event_labeler import (
    TESTS_EJECUTADOS_N4_MIN_DELTA_SECONDS,
    EpisodeContext,
    label_event,
)
from execution_service.services.ctr_emitter import build_payload, should_emit
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
    map_case,
)
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus

_AHORA = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)

# Los tres status que `result_mapper` manda a CaseStatus.ERROR y que un alumno
# real produce todo el tiempo. Ninguno es un fallo de infraestructura.
STATUS_DEL_ALUMNO_QUE_NO_SON_FAIL = [
    pytest.param(SandboxStatus.COMPILATION_ERROR, id="no-compila"),
    pytest.param(SandboxStatus.TIME_LIMIT_EXCEEDED, id="bucle-infinito-o-cold-start"),
    pytest.param(SandboxStatus.RUNTIME_ERROR_NZEC, id="excepcion-en-runtime"),
]

# El defecto esta ABIERTO: los dos tests de abajo describen la conducta correcta
# y hoy no se cumple. Van en xfail para que la rama no quede con rojos que se
# confundan con una regresion real — pero `strict=True` a proposito: el dia que
# alguien arregle el defecto, estos tests pasan, el xfail estricto los convierte
# en FALLO, y quien lo arreglo se entera de que tiene que venir a sacar el
# marcador. Un xfail no estricto se volveria mentira silenciosa.
#
# Al sacar el marcador, borrar tambien esta constante y el comentario.
DEFECTO_ABIERTO = pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECTO ABIERTO — `RunResult.failed` cuenta solo CaseStatus.FAIL, asi que "
        "una corrida donde todos los casos dieron ERROR (no compila / timeout / "
        "crash) emite `test_count_failed=0` y el labeler la etiqueta N4. Ver el "
        "docstring de este modulo y el informe 2026-07-30-analisis-pr-57-java-execution.md. "
        "El arreglo es una decision pedagogica pendiente (3 opciones, ninguna obvia)."
    ),
)


def _sandbox(status: SandboxStatus, *, stdout: str = "") -> SandboxResult:
    return SandboxResult(
        status=status,
        stdout=stdout,
        stderr="",
        compile_output="error: ';' expected" if status is SandboxStatus.COMPILATION_ERROR else "",
        time_seconds=0.4,
        memory_kb=14000,
    )


def _caso(status: SandboxStatus, *, case_id: str = "t1", stdout: str = "") -> CaseResult:
    return map_case(
        case_id=case_id,
        name="caso basico",
        case_type="stdin_stdout",
        stdin="",
        expected="Hola",
        weight=1.0,
        result=_sandbox(status, stdout=stdout),
    )


def _contexto_tutor_lejano() -> EpisodeContext:
    """El contexto que dispara la rama N4: el tutor respondio hace rato.

    Es el caso pedagogicamente interesante — el alumno valida solo, sin la
    influencia inmediata del tutor. Y es el que expone el defecto.
    """
    return EpisodeContext(
        event_ts=_AHORA,
        episode_started_at=_AHORA - timedelta(minutes=30),
        last_tutor_respondio_at=_AHORA
        - timedelta(seconds=TESTS_EJECUTADOS_N4_MIN_DELTA_SECONDS + 60),
    )


def _payload_de(run: RunResult) -> dict[str, object]:
    return build_payload(run, hidden_case_ids=set(), ejecucion_ms=1200, engine="docker-java")


# ── El test que protege el corpus ────────────────────────────────────────────


@DEFECTO_ABIERTO
@pytest.mark.parametrize("status", STATUS_DEL_ALUMNO_QUE_NO_SON_FAIL)
def test_una_corrida_sin_un_solo_caso_aprobado_no_puede_ser_n4(status: SandboxStatus) -> None:
    """**No borrar sin leer el docstring del modulo.**

    Cruza los dos servicios a proposito: el payload lo arma el emisor real del
    execution-service y lo etiqueta el labeler real del classifier-service. Es
    la unica forma de verificar la propiedad, porque vive ENTRE los dos y
    ninguno de los dos la puede probar solo.

    N4 es "apropiacion reflexiva", el nivel mas alto del modelo de la tesis.
    Cero casos aprobados no puede ser eso bajo ninguna lectura.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso(status, case_id="t1"), _caso(status, case_id="t2")],
    )
    payload = _payload_de(run)

    assert should_emit(run), (
        "precondicion del test: esta corrida SI se emite (no es fallo de infra). "
        "Si esto empieza a fallar, el defecto se arreglo cortando la emision."
    )
    assert payload["test_count_passed"] == 0, "precondicion: no aprobo ni un caso"

    nivel = label_event("tests_ejecutados", payload, context=_contexto_tutor_lejano())

    assert nivel != "N4", (
        f"corrida con 0 casos aprobados ({status.value}) etiquetada como apropiacion "
        f"reflexiva. `test_count_failed={payload['test_count_failed']}` y el labeler "
        "lee failed==0 como 'paso todo'. Contamina el corpus de la tesis inflando "
        "el nivel, que es lo que el docstring de ctr_emitter dice evitar."
    )


# ── La causa, aislada del labeler ────────────────────────────────────────────


@DEFECTO_ABIERTO
@pytest.mark.parametrize("status", STATUS_DEL_ALUMNO_QUE_NO_SON_FAIL)
def test_los_conteos_de_una_corrida_completada_cierran(status: SandboxStatus) -> None:
    """`passed + failed` tiene que dar `total` en una corrida que SI corrio.

    Es la misma propiedad que el test anterior, sin depender del classifier.
    Cualquier consumidor del payload —el labeler, el panel del docente, una
    query de la tesis— asume que los tres numeros cierran. Hoy un caso en
    ERROR se evapora: no suma a `passed` ni a `failed`, pero si a `total`.

    `INFRASTRUCTURE_FAILURE` queda fuera a proposito: ahi los tres son 0 por
    diseno (D4) y la propiedad se cumple trivialmente.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso(status, case_id="t1"), _caso(status, case_id="t2")],
    )

    assert run.total == 2, "los dos casos corrieron"
    assert run.passed + run.failed == run.total, (
        f"{run.passed} aprobados + {run.failed} fallidos != {run.total} corridos. "
        f"Los casos en {CaseStatus.ERROR.value} no entran en ninguno de los dos "
        "conteos y desaparecen del payload."
    )


# ── Controles: que el arreglo no rompa lo que SI funciona ────────────────────


def test_una_corrida_realmente_aprobada_si_es_n4() -> None:
    """Control del test principal.

    Sin esto, "romper N4 para siempre" pasaria los tests de arriba. La regla
    v1.2.0 del labeler tiene que seguir dando N4 cuando corresponde.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _caso(SandboxStatus.ACCEPTED, case_id="t1", stdout="Hola\n"),
            _caso(SandboxStatus.ACCEPTED, case_id="t2", stdout="Hola\n"),
        ],
    )
    payload = _payload_de(run)

    assert payload["test_count_passed"] == 2
    assert payload["test_count_failed"] == 0
    assert label_event("tests_ejecutados", payload, context=_contexto_tutor_lejano()) == "N4"


def test_una_corrida_con_fallos_reales_sigue_siendo_n3() -> None:
    """El otro control: `fail` genuino (salida incorrecta) sigue dando N3."""
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _caso(SandboxStatus.ACCEPTED, case_id="t1", stdout="Hola\n"),
            _caso(SandboxStatus.WRONG_ANSWER, case_id="t2", stdout="Chau\n"),
        ],
    )
    payload = _payload_de(run)

    assert payload["test_count_failed"] == 1
    assert label_event("tests_ejecutados", payload, context=_contexto_tutor_lejano()) == "N3"


def test_el_fallo_de_infraestructura_sigue_sin_emitirse() -> None:
    """Anti-regresion de lo que Juani YA resolvio bien.

    El arreglo del defecto de arriba no tiene que tocar esta propiedad.
    """
    from execution_service.services.result_mapper import infrastructure_failure

    assert not should_emit(infrastructure_failure("sandbox no alcanzable"))
