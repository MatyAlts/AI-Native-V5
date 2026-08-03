"""Smoke — soporte multi-lenguaje: ciclo de autoria de una TP Java.

Valida contra el stack real lo que la epic `java-language-model` dejo en pie:

  1. Crear un ejercicio Java con un test case `junit_assert`.
  2. Crear una TP Java y componerla con ese ejercicio.
  3. Publicarla.
  4. Rechazo de mezcla: agregar un ejercicio Python a esa TP -> 422.
  5. Rechazo de TP vacia al publicar -> 422.
  6. Filtro `?language=` en el banco.
  7. Anti-regresion: los pesos que no suman 1.0 NO bloquean la publicacion.

Por que smoke y no unit: los unit tests de esta epic corren con la DB mockeada.
Lo que se rompe en runtime y escapa a esos tests es exactamente esta clase de
cosa — el `MissingGreenlet` al resolver los ejercicios en `publish()` solo
aparece contra un driver async real, y el default `'python'` de la columna solo
se comporta como tal contra Postgres.

El punto 7 no es decorativo. Las 169 asociaciones ejercicio-TP del piloto tienen
`peso_en_tp = 1.0000` cada una, asi que toda TP de mas de un ejercicio suma > 1.0.
Si alguien reintroduce la regla de suma 1.0 creyendo que su ausencia fue un
olvido, este test lo frena antes de que 25 de las 27 TPs publicadas queden sin
poder republicarse.

Requiere:
  - academic-service en :8002 via api-gateway :8000
  - Casbin con ejercicio:CRUD y tarea_practica:CRUD para docente
  - Migracion 20260723_0001 aplicada (columna `language` en ambas tablas)
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from _helpers import COMISION_A_MANANA, DOCENTE_DEMO, TENANT_DEMO

# ── State compartido entre tests del modulo (secuenciales) ─────────────

_state: dict[str, str] = {}


def _docente_headers() -> dict[str, str]:
    return {
        "X-User-Id": DOCENTE_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }


def _ejercicio_payload(language: str, titulo: str) -> dict:
    """Ejercicio minimo valido, con el tipo de test case propio del lenguaje."""
    tipo = "junit_assert" if language == "java" else "pytest_assert"
    return {
        "titulo": titulo,
        "enunciado_md": f"Resolver el ejercicio en {language}.",
        "unidad_tematica": "smoke",
        "language": language,
        "test_cases": [
            {
                "id": "tc1",
                "name": "caso basico",
                "type": tipo,
                "code": "assert True",
                "is_public": True,
                "weight": 1.0,
            }
        ],
    }


def _tp_payload(language: str, codigo: str) -> dict:
    return {
        "comision_id": COMISION_A_MANANA,
        "codigo": codigo,
        "titulo": f"Smoke TP {language}",
        "enunciado": f"Trabajo practico de smoke en {language}.",
        "language": language,
    }


# ── Ciclo de autoria ───────────────────────────────────────────────────


@pytest.mark.smoke
def test_crear_ejercicio_java(client: httpx.Client) -> None:
    """El banco acepta un ejercicio Java con test case junit_assert."""
    resp = client.post(
        "/api/v1/ejercicios",
        json=_ejercicio_payload("java", f"Smoke Java {uuid4().hex[:8]}"),
        headers=_docente_headers(),
    )
    assert resp.status_code in (200, 201), f"create ejercicio java: {resp.status_code} {resp.text}"

    body = resp.json()
    UUID(body["id"])
    assert body["language"] == "java", f"language no persistio: {body}"
    assert body["test_cases"][0]["type"] == "junit_assert"

    _state["ejercicio_java_id"] = body["id"]


@pytest.mark.smoke
def test_crear_ejercicio_python_para_el_caso_negativo(client: httpx.Client) -> None:
    """Ejercicio Python que se usa mas abajo para probar el rechazo de mezcla."""
    resp = client.post(
        "/api/v1/ejercicios",
        json=_ejercicio_payload("python", f"Smoke Python {uuid4().hex[:8]}"),
        headers=_docente_headers(),
    )
    assert resp.status_code in (200, 201), (
        f"create ejercicio python: {resp.status_code} {resp.text}"
    )
    _state["ejercicio_python_id"] = resp.json()["id"]


@pytest.mark.smoke
def test_ejercicio_sin_language_queda_python(client: httpx.Client) -> None:
    """El default preserva la semantica del banco historico, integramente Python."""
    payload = _ejercicio_payload("python", f"Smoke default {uuid4().hex[:8]}")
    del payload["language"]

    resp = client.post("/api/v1/ejercicios", json=payload, headers=_docente_headers())
    assert resp.status_code in (200, 201), f"{resp.status_code} {resp.text}"
    assert resp.json()["language"] == "python"


@pytest.mark.smoke
def test_filtro_por_language_en_el_banco(client: httpx.Client) -> None:
    """`?language=java` devuelve solo Java; sin el parametro devuelve todo."""
    resp_java = client.get(
        "/api/v1/ejercicios", params={"language": "java", "limit": 100}, headers=_docente_headers()
    )
    assert resp_java.status_code == 200, f"{resp_java.status_code} {resp_java.text}"
    items = resp_java.json()["data"]
    assert items, "el filtro java no devolvio nada — el ejercicio del test anterior deberia estar"
    assert all(i["language"] == "java" for i in items), "el filtro dejo pasar otro lenguaje"

    resp_todos = client.get("/api/v1/ejercicios", params={"limit": 100}, headers=_docente_headers())
    assert resp_todos.status_code == 200
    lenguajes = {i["language"] for i in resp_todos.json()["data"]}
    assert "python" in lenguajes, "sin filtro deberia devolver tambien los Python del banco"


@pytest.mark.smoke
def test_crear_tp_java_y_componerla(client: httpx.Client) -> None:
    """TP Java + su ejercicio Java asociado."""
    resp_tp = client.post(
        "/api/v1/tareas-practicas",
        json=_tp_payload("java", f"SMK-J{uuid4().hex[:4].upper()}"),
        headers=_docente_headers(),
    )
    assert resp_tp.status_code in (200, 201), (
        f"create tp java: {resp_tp.status_code} {resp_tp.text}"
    )
    body = resp_tp.json()
    assert body["language"] == "java", f"language de la TP no persistio: {body}"
    _state["tp_java_id"] = body["id"]

    resp_add = client.post(
        f"/api/v1/tareas-practicas/{_state['tp_java_id']}/ejercicios",
        json={"ejercicio_id": _state["ejercicio_java_id"], "orden": 1, "peso_en_tp": "1.0"},
        headers=_docente_headers(),
    )
    assert resp_add.status_code in (200, 201), (
        f"add ejercicio: {resp_add.status_code} {resp_add.text}"
    )


@pytest.mark.smoke
def test_agregar_ejercicio_de_otro_lenguaje_da_422(client: httpx.Client) -> None:
    """El bloqueo es temprano: al componer, no al publicar.

    Un docente que arma una TP de 14 ejercicios tiene que enterarse al segundo.
    """
    resp = client.post(
        f"/api/v1/tareas-practicas/{_state['tp_java_id']}/ejercicios",
        json={"ejercicio_id": _state["ejercicio_python_id"], "orden": 2, "peso_en_tp": "1.0"},
        headers=_docente_headers(),
    )
    assert resp.status_code == 422, f"esperaba 422, dio {resp.status_code}: {resp.text}"

    detail = resp.text.lower()
    assert "java" in detail and "python" in detail, (
        f"el mensaje deberia nombrar los dos lenguajes para que el docente sepa que mezclo: {resp.text}"
    )


@pytest.mark.smoke
def test_publicar_tp_java(client: httpx.Client) -> None:
    """La TP Java bien compuesta se publica."""
    resp = client.post(
        f"/api/v1/tareas-practicas/{_state['tp_java_id']}/publish",
        headers=_docente_headers(),
    )
    assert resp.status_code in (200, 201), f"publish: {resp.status_code} {resp.text}"
    assert resp.json()["estado"] == "published"


# ── Rechazos ───────────────────────────────────────────────────────────


@pytest.mark.smoke
def test_publicar_tp_vacia_da_422(client: httpx.Client) -> None:
    """Sin ejercicios y sin test cases propios no llega al alumno.

    Hasta esta epic `publish()` solo miraba el estado, asi que una TP vacia se
    publicaba y el alumno abria un episodio sin nada que resolver.
    """
    resp_tp = client.post(
        "/api/v1/tareas-practicas",
        json=_tp_payload("python", f"SMK-V{uuid4().hex[:4].upper()}"),
        headers=_docente_headers(),
    )
    assert resp_tp.status_code in (200, 201), f"{resp_tp.status_code} {resp_tp.text}"
    tp_vacia_id = resp_tp.json()["id"]

    resp = client.post(
        f"/api/v1/tareas-practicas/{tp_vacia_id}/publish", headers=_docente_headers()
    )
    assert resp.status_code == 422, f"esperaba 422, dio {resp.status_code}: {resp.text}"
    assert "vacia" in resp.text.lower(), f"el mensaje deberia decir por que: {resp.text}"


@pytest.mark.smoke
def test_pesos_que_no_suman_uno_no_bloquean(client: httpx.Client) -> None:
    """ANTI-REGRESION — no borrar sin leer esto.

    La regla de "los pesos suman 1.0" se retiro tras medir la base del piloto:
    169 de 169 asociaciones tienen peso 1.0000, ningun calculo de calificacion
    consume el campo, y aplicarla habria impedido republicar 25 de las 27 TPs
    publicadas.

    Este test arma exactamente ese caso — 2 ejercicios de peso 1.0, suma 2.0 — y
    exige que publique. Si alguien reintroduce la regla creyendo que su ausencia
    fue un olvido, esto lo frena antes de romper el piloto.
    """
    resp_tp = client.post(
        "/api/v1/tareas-practicas",
        json=_tp_payload("python", f"SMK-P{uuid4().hex[:4].upper()}"),
        headers=_docente_headers(),
    )
    assert resp_tp.status_code in (200, 201), f"{resp_tp.status_code} {resp_tp.text}"
    tp_id = resp_tp.json()["id"]

    for orden in (1, 2):
        payload = _ejercicio_payload("python", f"Smoke peso {orden} {uuid4().hex[:8]}")
        ej_resp = client.post("/api/v1/ejercicios", json=payload, headers=_docente_headers())
        assert ej_resp.status_code in (200, 201), f"{ej_resp.status_code} {ej_resp.text}"

        add_resp = client.post(
            f"/api/v1/tareas-practicas/{tp_id}/ejercicios",
            json={
                "ejercicio_id": ej_resp.json()["id"],
                "orden": orden,
                "peso_en_tp": "1.0",  # suma final 2.0, la convencion real del piloto
            },
            headers=_docente_headers(),
        )
        assert add_resp.status_code in (200, 201), f"{add_resp.status_code} {add_resp.text}"

    resp = client.post(f"/api/v1/tareas-practicas/{tp_id}/publish", headers=_docente_headers())
    assert resp.status_code in (200, 201), (
        f"los pesos NO deben bloquear la publicacion: {resp.status_code} {resp.text}"
    )
