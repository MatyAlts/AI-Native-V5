"""Smoke — epic `java-execution-engine`: el alumno ejecuta Java server-side.

Cubre las tareas 8.1 (ciclo completo) y 8.2 (camino de fallo), contra el stack
real: el `execution-service` en :8013 hablando con el runner en :8015, que es el
unico con acceso a Docker (ADR-060).

Lo que estos tests atrapan y los unit no:

  - Que la cadena entera este cableada: gateway → execution-service → runner →
    contenedor → resultado traducido al formato del sistema.
  - Que un caso OCULTO se ejecute server-side sin viajar al navegador. Es la
    propiedad que la ejecucion en Pyodide no podia dar, y la que justifica todo
    el servicio.
  - Que un fallo de infraestructura se distinga de casos fallidos. Esa
    distincion protege el corpus de la tesis: el clasificador usa el conteo de
    fallidos para separar dos niveles de apropiacion.

Requiere, ademas del stack habitual:
  - `execution-service` en :8013 y `execution-runner` en :8015
  - Docker corriendo, con la imagen de JDK disponible
"""

from __future__ import annotations

import time
from uuid import uuid4

import httpx
import pytest
from _helpers import DOCENTE_DEMO, TENANT_DEMO

ALUMNO_DEMO = "b1b1b1b1-0001-0001-0001-000000000001"
EXECUTION_URL = "http://127.0.0.1:8013"

JAVA_OK = (
    'public class Main { public static void main(String[] a){ System.out.println("Hola Mundo"); } }'
)
JAVA_NO_COMPILA = (
    'public class Main { public static void main(String[] a){ System.out.println("x") } }'
)

_state: dict[str, str] = {}


def _docente() -> dict[str, str]:
    return {
        "X-User-Id": DOCENTE_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }


def _alumno() -> dict[str, str]:
    return {
        "X-User-Id": ALUMNO_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "alumno01@demo-uni.edu",
        "X-User-Roles": "estudiante",
    }


def _ejecutar(source: str, ejercicio_id: str, *, timeout: float = 90.0) -> dict:
    """Pide una ejecucion y espera el resultado. Devuelve el `result`."""
    with httpx.Client(base_url=EXECUTION_URL, timeout=30.0) as c:
        resp = c.post(
            "/api/v1/executions",
            json={"ejercicio_id": ejercicio_id, "source_code": source},
            headers=_alumno(),
        )
        assert resp.status_code == 202, f"{resp.status_code} {resp.text}"
        execution_id = resp.json()["execution_id"]

        deadline = time.time() + timeout
        while time.time() < deadline:
            estado = c.get(f"/api/v1/executions/{execution_id}", headers=_alumno())
            assert estado.status_code == 200, f"{estado.status_code} {estado.text}"
            body = estado.json()
            if body["state"] == "done":
                assert body["result"] is not None, "estado done sin resultado"
                return body["result"]
            time.sleep(0.5)
    raise AssertionError("la ejecucion no termino dentro del timeout")


@pytest.mark.smoke
def test_preparar_ejercicio_java_con_caso_oculto() -> None:
    """Ejercicio con un caso publico y uno OCULTO, para verificar los dos caminos."""
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15.0) as c:
        resp = c.post(
            "/api/v1/ejercicios",
            json={
                "titulo": f"Smoke ejecucion Java {uuid4().hex[:8]}",
                "enunciado_md": "Imprimir Hola Mundo.",
                "unidad_tematica": "smoke",
                "language": "java",
                "test_cases": [
                    {
                        "id": "publico",
                        "name": "salida visible",
                        "type": "stdin_stdout",
                        "code": "",
                        "expected": "Hola Mundo",
                        "is_public": True,
                        "weight": 1.0,
                    },
                    {
                        "id": "oculto",
                        "name": "SECRETO-DEL-CASO-OCULTO",
                        "type": "stdin_stdout",
                        "code": "",
                        "expected": "Hola Mundo",
                        "is_public": False,
                        "weight": 2.0,
                    },
                ],
            },
            headers=_docente(),
        )
        assert resp.status_code in (200, 201), f"{resp.status_code} {resp.text}"
        _state["ejercicio_id"] = resp.json()["id"]


@pytest.mark.smoke
def test_ciclo_completo_el_alumno_ejecuta_y_pasa() -> None:
    """Tarea 8.1 — el ciclo entero contra el stack real.

    Java REAL: `javac` + JVM en un contenedor efimero, no un doble.
    """
    result = _ejecutar(JAVA_OK, _state["ejercicio_id"])

    assert result["outcome"] == "completed", result
    assert result["total"] == 2, "corrieron el publico Y el oculto"
    assert result["passed"] == 2
    assert result["failed"] == 0


@pytest.mark.smoke
def test_el_caso_oculto_se_ejecuta_pero_no_se_revela() -> None:
    """La propiedad que la ejecucion en el navegador NO podia dar.

    Para correr un caso oculto client-side habria que mandarselo al alumno, y
    ahi deja de ser oculto. Server-side se ejecuta sin que viaje.
    """
    result = _ejecutar(JAVA_OK, _state["ejercicio_id"])

    ocultos = [c for c in result["cases"] if not c["is_public"]]
    assert len(ocultos) == 1, "el oculto tiene que estar en el resultado"
    assert ocultos[0]["status"] == "pass", "y tiene que haberse EJECUTADO"

    serializado = str(result)
    assert "SECRETO-DEL-CASO-OCULTO" not in serializado, "FUGA: el nombre del caso oculto"
    assert ocultos[0]["expected"] is None, "no viaja la salida esperada"
    assert ocultos[0]["got"] is None, "ni lo que imprimio (lo revelaria por diferencia)"


@pytest.mark.smoke
def test_un_error_de_compilacion_no_es_un_fallo_de_infraestructura() -> None:
    """Tarea 8.2, primer camino: el codigo del alumno esta mal.

    El error de `javac` llega con su formato real, que es el que el frontend
    parsea para marcar la linea.
    """
    result = _ejecutar(JAVA_NO_COMPILA, _state["ejercicio_id"])

    assert result["outcome"] != "infrastructure_failure", (
        "un error de compilacion es del alumno, NO de la infraestructura"
    )
    assert result["passed"] == 0

    publico = next(c for c in result["cases"] if c["is_public"])
    assert publico["status"] == "error"
    assert "error:" in (publico["error"] or ""), (
        f"deberia traer el mensaje de javac: {publico['error']!r}"
    )


@pytest.mark.smoke
def test_un_bucle_infinito_se_corta_y_no_cuelga_al_alumno() -> None:
    """El limite de wall time del contenedor, contra el stack real."""
    result = _ejecutar(
        "public class Main { public static void main(String[] a){ while(true){} } }",
        _state["ejercicio_id"],
        timeout=120.0,
    )
    assert result["outcome"] != "infrastructure_failure"
    publico = next(c for c in result["cases"] if c["is_public"])
    assert publico["status"] == "error", "un timeout es error, no un caso fallado"


@pytest.mark.smoke
def test_el_runner_rechaza_a_quien_no_tiene_el_token() -> None:
    """Gate D3 del ADR-060: el runner es el unico con acceso a Docker.

    Si esto empieza a devolver 200 sin token, cualquiera con acceso a la red
    interna puede pedir ejecuciones arbitrarias.

    Se saltea si el runner corre sin token (modo desarrollo local).
    """
    with httpx.Client(base_url="http://127.0.0.1:8015", timeout=20.0) as c:
        resp = c.post("/run", json={"source_code": JAVA_OK, "stdin": ""})

    if resp.status_code == 200:
        pytest.skip(
            "el runner corre sin RUNNER_TOKEN (modo dev). En produccion el token "
            "va SIEMPRE y el runner no se expone fuera de la red interna."
        )
    assert resp.status_code == 401, f"esperaba 401 sin token, dio {resp.status_code}"
