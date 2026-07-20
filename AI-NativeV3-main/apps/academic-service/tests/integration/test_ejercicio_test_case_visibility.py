"""A0.3 — Los test cases ocultos y el material de solución NO se filtran al alumno.

Bug: `GET /tareas-practicas/{id}/ejercicios` (y el detalle de la TP monolítica,
y `GET /ejercicios/{id}`) devolvían el Ejercicio COMPLETO a cualquiera con
`tarea_practica:read` / `ejercicio:read` — incluidos los estudiantes. Un alumno
podía leer los test cases ocultos (`is_public=false`, con la respuesta esperada),
las pistas de solución (`respuesta_pista`), el banco socrático, etc.

Fix: `academic_service.services.content_visibility` sanea la vista del alumno.
Estos tests cubren:
  1. El saneo puro (funciones sobre schemas).
  2. El endpoint `/tareas-practicas/{id}/ejercicios` por rol (alumno vs docente).
  3. El endpoint de detalle de TP monolítica por rol.

Estilo route-level: `TestClient(app)` + `dependency_overrides` (como
`test_materias_mias.py`). Se monkeypatchea `check_permission` (para no pegarle a
la DB de Casbin), `assert_comision_access` (contrato staff/alumno sin DB) y los
métodos de servicio que tocan Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User, get_current_user, get_db
from academic_service.main import app
from academic_service.schemas.tarea_practica import TareaPracticaOut
from academic_service.services.content_visibility import (
    sanitize_ejercicio_for_student,
    sanitize_tarea_practica_for_student,
)
from fastapi.testclient import TestClient
from platform_contracts.academic.ejercicio import EjercicioRead

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

_PUBLIC_TC = {
    "id": "tc-pub",
    "name": "caso publico",
    "type": "stdin_stdout",
    "code": "2 3",
    "expected": "5",
    "is_public": True,
    "weight": 1.0,
}
_HIDDEN_TC = {
    "id": "tc-oculto",
    "name": "caso oculto",
    "type": "stdin_stdout",
    "code": "99 1",
    "expected": "RESPUESTA_SECRETA_100",
    "is_public": False,
    "weight": 1.0,
}


def _ejercicio_attrs() -> SimpleNamespace:
    """Objeto ORM-like con TODOS los campos (públicos y de solución)."""
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=TENANT,
        titulo="Suma de dos numeros",
        enunciado_md="Leer dos enteros e imprimir su suma.",
        inicial_codigo="# TODO",
        materia_id=uuid4(),
        unidad_tematica="secuenciales",
        dificultad="basica",
        prerequisitos={"sintacticos": [], "conceptuales": []},
        test_cases=[dict(_PUBLIC_TC), dict(_HIDDEN_TC)],
        rubrica={"criterios": []},
        tutor_rules={
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": False,
            "nivel_socratico_minimo": 1,
            "instrucciones_adicionales": None,
        },
        banco_preguntas={
            "n1": [
                {
                    "texto": "que hace input()?",
                    "senal_comprension": "sabe leer",
                    "senal_alerta": "no sabe",
                }
            ],
            "n2": [],
            "n3": [],
            "n4": [],
        },
        misconceptions=[
            {
                "descripcion": "concatena strings en vez de sumar",
                "probabilidad_estimada": 0.6,
                "pregunta_diagnostica": "que tipo devuelve input()?",
            }
        ],
        respuesta_pista=[{"nivel": 4, "pista": "PISTA_SOLUCION: usa int() y +"}],
        heuristica_cierre={"tests_min_pasados": 1, "heuristica": "cierra si pasa el publico"},
        anti_patrones=[
            {
                "patron": "dar codigo",
                "descripcion": "no dar la solucion",
                "mensaje_orientacion": "pregunta",
            }
        ],
        created_by=uuid4(),
        created_via_ai=False,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        deleted_at=None,
    )


def _tp_attrs(
    *, estado: str = "published", test_cases: list[dict] | None = None
) -> SimpleNamespace:
    """TareaPractica ORM-like para el detalle monolítico."""
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=TENANT,
        comision_id=uuid4(),
        codigo="TP1",
        titulo="TP monolitica",
        enunciado="Resolver...",
        inicial_codigo=None,
        fecha_inicio=None,
        fecha_fin=None,
        peso=Decimal("1.0"),
        rubrica=None,
        test_cases=[dict(_PUBLIC_TC), dict(_HIDDEN_TC)] if test_cases is None else test_cases,
        permite_pausa=True,
        estado=estado,
        version=1,
        parent_tarea_id=None,
        template_id=None,
        has_drift=False,
        created_via_ai=False,
        unidad_id=None,
        created_by=uuid4(),
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        deleted_at=None,
    )


# ── 1. Saneo puro ────────────────────────────────────────────────────────────


def test_sanitize_ejercicio_oculta_solucion() -> None:
    ej = EjercicioRead.model_validate(_ejercicio_attrs())
    # Precondición: el objeto completo trae la solución.
    assert len(ej.test_cases) == 2
    assert ej.respuesta_pista and ej.tutor_rules is not None

    saneado = sanitize_ejercicio_for_student(ej)

    # Solo el test case público sobrevive, y sin el oculto (respuesta esperada).
    assert [tc.id for tc in saneado.test_cases] == ["tc-pub"]
    assert all(tc.is_public for tc in saneado.test_cases)
    assert "RESPUESTA_SECRETA_100" not in saneado.model_dump_json()
    # Material de solución / conducción del tutor: vaciado.
    assert saneado.respuesta_pista == []
    assert saneado.misconceptions == []
    assert saneado.banco_preguntas is None
    assert saneado.heuristica_cierre is None
    assert saneado.anti_patrones == []
    assert saneado.tutor_rules is None
    # El alumno conserva lo que necesita.
    assert saneado.enunciado_md == ej.enunciado_md
    assert saneado.inicial_codigo == ej.inicial_codigo
    # El original NO se muta (model_copy devuelve copia).
    assert len(ej.test_cases) == 2


def test_sanitize_tarea_practica_oculta_tests_privados() -> None:
    tp = TareaPracticaOut.model_validate(_tp_attrs())
    assert len(tp.test_cases) == 2

    saneado = sanitize_tarea_practica_for_student(tp)

    assert len(saneado.test_cases) == 1
    assert saneado.test_cases[0]["id"] == "tc-pub"
    assert "RESPUESTA_SECRETA_100" not in saneado.model_dump_json()


def test_sanitize_tarea_practica_fail_closed_sin_is_public() -> None:
    """Un test sin la clave `is_public` se trata como oculto (fail-closed)."""
    tc_sin_flag = {"id": "x", "name": "n", "type": "stdin_stdout", "expected": "OCULTO"}
    tp = TareaPracticaOut.model_validate(_tp_attrs(test_cases=[dict(_PUBLIC_TC), tc_sin_flag]))

    saneado = sanitize_tarea_practica_for_student(tp)

    assert [tc["id"] for tc in saneado.test_cases] == ["tc-pub"]


# ── 2/3. Route-level: filtrado por rol ───────────────────────────────────────


@pytest.fixture
def wired(monkeypatch):
    """Cablea app con auth/DB mockeados y servicios monkeypatcheados.

    Devuelve `set_role(role)` que instala un `User` con ese rol y un cliente.
    """
    from academic_service.routes import tareas_practicas as tp_routes
    from academic_service.services.tarea_practica_service import TareaPracticaService
    from academic_service.services.tp_ejercicio_service import TpEjercicioService

    _STAFF = {"superadmin", "docente_admin", "docente", "jtp", "auxiliar", "tutor_service"}

    # Casbin: permitir todo sin pegarle a la DB.
    monkeypatch.setattr(
        "academic_service.auth.casbin_setup.check_permission",
        lambda user, resource, action: True,
    )

    # assert_comision_access: contrato staff→True / alumno inscripto→False, sin DB.
    async def _fake_access(db, user, comision_id):
        return bool(user.roles & _STAFF)

    monkeypatch.setattr(tp_routes, "assert_comision_access", _fake_access)

    tp_holder: dict[str, SimpleNamespace] = {"tp": _tp_attrs()}

    async def _fake_get(self, tarea_id):
        return tp_holder["tp"]

    async def _fake_list_by_tp(self, tarea_id):
        ej = _ejercicio_attrs()
        pair = SimpleNamespace(
            id=uuid4(),
            tarea_practica_id=tarea_id,
            ejercicio_id=ej.id,
            orden=1,
            peso_en_tp=Decimal("1.0"),
        )
        return [(pair, ej)]

    monkeypatch.setattr(TareaPracticaService, "get", _fake_get)
    monkeypatch.setattr(TpEjercicioService, "list_by_tp", _fake_list_by_tp)

    role_holder: dict[str, str] = {"role": "estudiante"}

    async def _override_user() -> User:
        return User(
            id=uuid4(),
            tenant_id=TENANT,
            email="u@demo.edu",
            roles=frozenset({role_holder["role"]}),
            realm=str(TENANT),
        )

    async def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    def set_role(role: str) -> TestClient:
        role_holder["role"] = role
        return TestClient(app)

    try:
        yield set_role, tp_holder
    finally:
        app.dependency_overrides.clear()


def test_estudiante_no_recibe_tests_ocultos_ni_soluciones_en_ejercicios(wired) -> None:
    set_role, _ = wired
    client = set_role("estudiante")

    r = client.get(f"/api/v1/tareas-practicas/{uuid4()}/ejercicios")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    ej = body[0]["ejercicio"]

    # Solo test case público; el oculto y su respuesta esperada NO viajan.
    assert [tc["id"] for tc in ej["test_cases"]] == ["tc-pub"]
    assert "RESPUESTA_SECRETA_100" not in r.text
    # Material de solución / guion del tutor: no presente.
    assert ej["respuesta_pista"] == []
    assert ej["misconceptions"] == []
    assert ej["banco_preguntas"] is None
    assert ej["tutor_rules"] is None
    assert ej["heuristica_cierre"] is None
    assert ej["anti_patrones"] == []
    # Enunciado sí presente (lo necesita para resolver).
    assert ej["enunciado_md"]


def test_docente_recibe_ejercicio_completo(wired) -> None:
    set_role, _ = wired
    client = set_role("docente")

    r = client.get(f"/api/v1/tareas-practicas/{uuid4()}/ejercicios")
    assert r.status_code == 200
    ej = r.json()[0]["ejercicio"]

    # El docente ve TODO (autoría/corrección).
    assert {tc["id"] for tc in ej["test_cases"]} == {"tc-pub", "tc-oculto"}
    assert "RESPUESTA_SECRETA_100" in r.text
    assert ej["respuesta_pista"], "el docente debe ver las pistas de solución"
    assert ej["tutor_rules"] is not None


def test_tutor_service_recibe_ejercicio_completo(wired) -> None:
    """El tutor-service inyecta el contexto socrático completo al LLM (ADR-048/049)."""
    set_role, _ = wired
    client = set_role("tutor_service")

    r = client.get(f"/api/v1/tareas-practicas/{uuid4()}/ejercicios")
    assert r.status_code == 200
    ej = r.json()[0]["ejercicio"]
    assert len(ej["test_cases"]) == 2
    assert ej["respuesta_pista"]


def test_estudiante_no_ve_test_cases_ocultos_en_tp_monolitica(wired) -> None:
    set_role, tp_holder = wired
    tp_holder["tp"] = _tp_attrs(estado="published")
    client = set_role("estudiante")

    r = client.get(f"/api/v1/tareas-practicas/{tp_holder['tp'].id}")
    assert r.status_code == 200
    body = r.json()
    assert [tc["id"] for tc in body["test_cases"]] == ["tc-pub"]
    assert "RESPUESTA_SECRETA_100" not in r.text


def test_docente_ve_test_cases_ocultos_en_tp_monolitica(wired) -> None:
    set_role, tp_holder = wired
    tp_holder["tp"] = _tp_attrs(estado="published")
    client = set_role("docente")

    r = client.get(f"/api/v1/tareas-practicas/{tp_holder['tp'].id}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["test_cases"]) == 2
    assert "RESPUESTA_SECRETA_100" in r.text
