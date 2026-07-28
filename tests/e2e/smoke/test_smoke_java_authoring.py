"""Smoke — epic `java-authoring-experience`: el lenguaje llega hasta el alumno.

La epic anterior (`java-language-model`) dejo el lenguaje en la base y en los
contratos, y su smoke (`test_smoke_java_language.py`) cubre el ciclo de autoria
del docente. Lo que ESTA epic agrega y se verifica acá es lo que ningun unit
test alcanza:

  1. El endpoint que resuelve los ejercicios de una TP devuelve `language` **al
     alumno**, y sobrevive el saneado por rol. Ese saneado usa
     `model_copy(update=...)`: alcanza con que alguien agregue `language` a la
     lista de campos que pisa para que el editor del alumno vuelva a Python sin
     que falle nada.
  2. `junit_assert` viaja intacto hasta el alumno. El frontend despacha el
     runner por ese valor; si el backend lo normalizara, un caso de Java
     terminaria corriendo contra Pyodide.
  3. Las variantes de prompt por lenguaje son resolubles en governance. La
     resolucion (`services/prompt_variants.py`) construye el nombre de familia
     con un sufijo: si el directorio no existe, `POST /generate` muere con un
     502 que no dice que falta un archivo.

Requiere:
  - academic-service y governance-service arriba, via api-gateway :8000
  - Migracion 20260723_0001 aplicada
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from _helpers import COMISION_A_MANANA, DOCENTE_DEMO, TENANT_DEMO

# Alumno del seed `seed-3-comisiones` inscripto en A-Manana.
ALUMNO_DEMO = "b1b1b1b1-0001-0001-0001-000000000001"

_state: dict[str, str] = {}


def _docente_headers() -> dict[str, str]:
    return {
        "X-User-Id": DOCENTE_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }


def _alumno_headers() -> dict[str, str]:
    return {
        "X-User-Id": ALUMNO_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "alumno01@demo-uni.edu",
        "X-User-Roles": "estudiante",
    }


@pytest.mark.smoke
def test_preparar_tp_java_publicada(client: httpx.Client) -> None:
    """Arma una TP Java publicada con un ejercicio que tiene caso junit_assert."""
    ej = client.post(
        "/api/v1/ejercicios",
        json={
            "titulo": f"Smoke authoring Java {uuid4().hex[:8]}",
            "enunciado_md": "Imprimir un saludo.",
            "unidad_tematica": "smoke",
            "language": "java",
            "inicial_codigo": "public class Main {\n    public static void main(String[] args) {\n    }\n}\n",
            "test_cases": [
                {
                    "id": "tc1",
                    "name": "salida esperada",
                    "type": "junit_assert",
                    "code": 'assertEquals("Hola", out.trim());',
                    "is_public": True,
                    "weight": 1.0,
                }
            ],
        },
        headers=_docente_headers(),
    )
    assert ej.status_code in (200, 201), f"{ej.status_code} {ej.text}"
    _state["ejercicio_id"] = ej.json()["id"]

    tp = client.post(
        "/api/v1/tareas-practicas",
        json={
            "comision_id": COMISION_A_MANANA,
            "codigo": f"SMK-A{uuid4().hex[:4].upper()}",
            "titulo": "Smoke authoring TP Java",
            "enunciado": "TP de smoke de la epic de autoria.",
            "language": "java",
        },
        headers=_docente_headers(),
    )
    assert tp.status_code in (200, 201), f"{tp.status_code} {tp.text}"
    _state["tp_id"] = tp.json()["id"]

    add = client.post(
        f"/api/v1/tareas-practicas/{_state['tp_id']}/ejercicios",
        json={"ejercicio_id": _state["ejercicio_id"], "orden": 1, "peso_en_tp": "1.0"},
        headers=_docente_headers(),
    )
    assert add.status_code in (200, 201), f"{add.status_code} {add.text}"

    pub = client.post(
        f"/api/v1/tareas-practicas/{_state['tp_id']}/publish", headers=_docente_headers()
    )
    assert pub.status_code in (200, 201), f"{pub.status_code} {pub.text}"


@pytest.mark.smoke
def test_el_alumno_recibe_el_lenguaje_del_ejercicio(client: httpx.Client) -> None:
    """El campo sobrevive el saneado por rol.

    Sin esto el editor del alumno no tiene como saber en que lenguaje esta el
    ejercicio, y vuelve al Python fijo que esta epic elimino.
    """
    resp = client.get(
        f"/api/v1/tareas-practicas/{_state['tp_id']}/ejercicios", headers=_alumno_headers()
    )
    assert resp.status_code == 200, f"{resp.status_code} {resp.text}"

    pares = resp.json()
    assert pares, "la TP publicada deberia exponer su ejercicio al alumno"

    ejercicio = pares[0]["ejercicio"]
    assert ejercicio.get("language") == "java", (
        f"el alumno no recibio el lenguaje — revisar `content_visibility.py`, "
        f"el saneado no debe pisar `language`: {ejercicio}"
    )


@pytest.mark.smoke
def test_el_alumno_recibe_el_tipo_de_caso_de_java(client: httpx.Client) -> None:
    """`junit_assert` llega sin normalizar.

    El frontend despacha el runner por este valor. Si el backend lo colapsara a
    `pytest_assert`, un caso de Java se correria contra Pyodide y devolveria un
    veredicto que no significa nada.
    """
    resp = client.get(
        f"/api/v1/tareas-practicas/{_state['tp_id']}/ejercicios", headers=_alumno_headers()
    )
    assert resp.status_code == 200, f"{resp.status_code} {resp.text}"

    tipos = [tc["type"] for tc in resp.json()[0]["ejercicio"]["test_cases"]]
    assert "junit_assert" in tipos, f"el tipo de Java no llego al alumno: {tipos}"


@pytest.mark.smoke
def test_la_tp_declara_su_lenguaje_al_alumno(client: httpx.Client) -> None:
    """El selector de tareas rotula por este campo, antes de abrir el episodio."""
    resp = client.get(f"/api/v1/tareas-practicas/{_state['tp_id']}", headers=_alumno_headers())
    assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
    assert resp.json().get("language") == "java", f"la TP no declara su lenguaje: {resp.text}"


@pytest.mark.smoke
@pytest.mark.parametrize(
    "prompt_name",
    [
        "ejercicio_generator",
        "ejercicio_generator_java",
        "tp_generator",
        "tp_generator_java",
    ],
)
def test_las_variantes_de_prompt_por_lenguaje_son_resolubles(
    client: httpx.Client, prompt_name: str
) -> None:
    """Cada familia alcanzable desde `resolve_prompt_name` existe en governance.

    El governance-service esta FUERA del ROUTE_MAP del gateway by-design, asi
    que se lo consulta directo. Si una variante falta, la generacion por IA para
    ese lenguaje devuelve un 502 generico que no dice que falta un directorio.
    """
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=10.0) as gov:
        resp = gov.get(f"/api/v1/prompts/{prompt_name}/v1.0.0")

    assert resp.status_code == 200, (
        f"prompt '{prompt_name}' no resoluble ({resp.status_code}). "
        f"Toda variante que `resolve_prompt_name` pueda construir necesita su "
        f"directorio en `ai-native-prompts/prompts/`."
    )
    assert resp.json().get("content"), f"prompt '{prompt_name}' vino vacio"
