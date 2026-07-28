"""Tarea 3.5 — ninguna respuesta al cliente filtra un caso oculto.

**No borrar ni relajar sin leer esto.**

El execution-service lee los ejercicios con el rol `execution_service`, que esta
en `FULL_CONTENT_ROLES`: ve los casos ocultos con su `expected` (la respuesta
correcta). Ese privilegio existe para poder EJECUTARLOS server-side, que es la
propiedad que la ejecucion en el navegador no podia dar.

Si esa informacion se filtrara en la respuesta, el privilegio se convierte en la
fuga que la ejecucion client-side justamente evitaba: un alumno abriendo las
herramientas de desarrollo leeria las soluciones.

Los tests se escriben sobre el JSON **serializado**, no sobre los dataclasses:
lo que importa no es lo que el objeto tenga en memoria, sino lo que viaja por el
cable.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.executor import to_client_payload
from execution_service.services.judge0_client import Judge0Result, Judge0Status
from execution_service.services.result_mapper import RunOutcome, RunResult, map_case

# Marcadores que NO deben aparecer nunca en el payload. Son los datos que
# permitirian resolver el ejercicio sin pensarlo.
SECRETO_EXPECTED = "42-RESPUESTA-SECRETA"
SECRETO_CODE = "assertEquals(42, Calculadora.responder());"
SECRETO_NAME = "verifica el algoritmo de Fibonacci optimizado"
SECRETO_ID = "tc-oculto-real"


def _ejercicio() -> Ejercicio:
    return Ejercicio(
        id=uuid4(),
        language="java",
        inicial_codigo="public class Main {}",
        test_cases=[
            TestCase(
                id="tc-publico",
                name="caso visible",
                type="stdin_stdout",
                code="5",
                expected="10",
                is_public=True,
                weight=1.0,
            ),
            TestCase(
                id=SECRETO_ID,
                name=SECRETO_NAME,
                type="junit_assert",
                code=SECRETO_CODE,
                expected=SECRETO_EXPECTED,
                is_public=False,
                weight=2.0,
            ),
        ],
    )


def _run(ej: Ejercicio, *, oculto_status: Judge0Status) -> RunResult:
    cases = []
    for tc in ej.test_cases:
        status = Judge0Status.ACCEPTED if tc.is_public else oculto_status
        cases.append(
            map_case(
                case_id=tc.id,
                name=tc.name,
                case_type=tc.type,
                stdin=tc.code,
                expected=tc.expected,
                weight=tc.weight,
                result=Judge0Result(
                    status=status,
                    stdout=SECRETO_EXPECTED if not tc.is_public else "10",
                    stderr="",
                    compile_output="",
                    time_seconds=0.3,
                    memory_kb=1000,
                ),
            )
        )
    return RunResult(outcome=RunOutcome.COMPLETED, cases=cases)


@pytest.mark.parametrize(
    "oculto_status",
    [Judge0Status.ACCEPTED, Judge0Status.WRONG_ANSWER, Judge0Status.RUNTIME_ERROR_NZEC],
)
def test_el_payload_no_contiene_datos_del_caso_oculto(oculto_status: Judge0Status) -> None:
    """Pase, falle o explote, el caso oculto nunca revela su contenido."""
    ej = _ejercicio()
    payload = to_client_payload(_run(ej, oculto_status=oculto_status), ej)
    serializado = json.dumps(payload, ensure_ascii=False)

    for secreto, que_es in [
        (SECRETO_EXPECTED, "la salida esperada"),
        (SECRETO_CODE, "el codigo del assert"),
        (SECRETO_NAME, "el nombre del caso"),
        (SECRETO_ID, "el id real"),
    ]:
        assert secreto not in serializado, (
            f"FUGA: {que_es} de un caso oculto salio en la respuesta al cliente.\n"
            f"payload: {serializado}"
        )


def test_el_alumno_igual_sabe_cuantos_ocultos_hay_y_si_paso() -> None:
    """Ocultar el contenido no es ocultar la existencia.

    El alumno necesita saber que hay casos que no ve y si los paso — si no, no
    entiende por que su nota no es la que espera.
    """
    ej = _ejercicio()
    payload = to_client_payload(_run(ej, oculto_status=Judge0Status.WRONG_ANSWER), ej)

    ocultos = [c for c in payload["cases"] if not c["is_public"]]
    assert len(ocultos) == 1
    assert ocultos[0]["status"] == "fail", "el alumno sabe que lo fallo"
    assert ocultos[0]["name"] == "Caso oculto 1", "rotulo generico, posicional"
    assert ocultos[0]["weight"] == 2.0, "el peso si es publico: afecta su nota"


def test_el_caso_publico_conserva_todos_sus_datos() -> None:
    """El contraste: sobre lo publico no se oculta nada.

    Si este test falla junto con los de arriba, alguien 'arreglo' la fuga
    borrando datos de mas y rompio el feedback del alumno.
    """
    ej = _ejercicio()
    payload = to_client_payload(_run(ej, oculto_status=Judge0Status.ACCEPTED), ej)

    publico = next(c for c in payload["cases"] if c["is_public"])
    assert publico["name"] == "caso visible"
    assert publico["input"] == "5"
    assert publico["expected"] == "10"
    assert publico["got"] == "10"


def test_el_motivo_interno_de_un_fallo_de_infra_no_sale_al_cliente() -> None:
    """`compile_output` transporta el motivo interno ante fallo de infra.

    Ese texto lleva detalle de nuestra infraestructura ("sandbox no alcanzable:
    ConnectError"), que no le sirve al alumno y no deberia exponerse.
    """
    from execution_service.services.result_mapper import infrastructure_failure

    ej = _ejercicio()
    run = infrastructure_failure("sandbox no alcanzable: ConnectError en judge0.internal:2358")
    payload = to_client_payload(run, ej)

    assert payload["compile_output"] == ""
    assert "judge0.internal" not in json.dumps(payload)
    assert payload["outcome"] == "infrastructure_failure"
    assert payload["failed"] == 0, "un fallo de infra no cuenta como casos fallidos"
