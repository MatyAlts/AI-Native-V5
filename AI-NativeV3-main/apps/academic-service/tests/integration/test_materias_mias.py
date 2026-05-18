"""Tests del endpoint GET /api/v1/materias/mias.

Cubren el query SQL flatten que junta Inscripcion + Comision + Materia +
Periodo y devuelve una fila por inscripción activa. Mock-based: probamos
la transformación a `MateriaInscripta` y el caso vacío. La RLS por tenant
queda cubierta por `test_rls_isolation.py` (corre con DB real).

Diseño: el alumno NO elige comisión, elige materia. Por eso el endpoint
filtra por `student_pseudonym = user.id` (header injectado por api-gateway).
Cierra el bug conocido de `/comisiones/mis` que joinea contra
`usuarios_comision` (docentes/JTP) — devolvía [] para estudiantes.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from academic_service.auth.dependencies import User, get_current_user, get_db
from academic_service.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def tenant_a_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def student_id() -> UUID:
    return UUID("b1b1b1b1-0001-0001-0001-000000000001")


def _row(
    *,
    materia_id: UUID,
    materia_codigo: str,
    materia_nombre: str,
    comision_id: UUID,
    comision_codigo: str,
    comision_nombre: str | None,
    horario: dict | None,
    periodo_id: UUID,
    periodo_codigo: str,
    inscripcion_id: UUID,
    fecha_inscripcion: date,
) -> dict:
    """Fabrica una fila como las que devuelve `result.mappings().all()`."""
    return {
        "materia_id": materia_id,
        "materia_codigo": materia_codigo,
        "materia_nombre": materia_nombre,
        "comision_id": comision_id,
        "comision_codigo": comision_codigo,
        "comision_nombre": comision_nombre,
        "comision_horario": horario or {},
        "periodo_id": periodo_id,
        "periodo_codigo": periodo_codigo,
        "inscripcion_id": inscripcion_id,
        "fecha_inscripcion": fecha_inscripcion,
    }


def _build_session_mock(rows: list[dict]) -> MagicMock:
    """Mockea AsyncSession.execute para que devuelva `rows` via mappings()."""
    mappings = MagicMock()
    mappings.all = MagicMock(return_value=rows)
    result = MagicMock()
    result.mappings = MagicMock(return_value=mappings)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.fixture
def client_estudiante(tenant_a_id: UUID, student_id: UUID):
    """Cliente FastAPI con `user=estudiante` y `session` mockeable.

    El test inyecta las filas que `session.execute` devuelve via fixture
    `set_rows`. Limpia overrides al teardown para no contaminar otros tests.
    """
    rows_holder: dict[str, list[dict]] = {"rows": []}

    async def _override_user() -> User:
        return User(
            id=student_id,
            tenant_id=tenant_a_id,
            email="estudiante@demo.edu",
            roles=frozenset({"estudiante"}),
            realm=str(tenant_a_id),
        )

    async def _override_db():
        session = _build_session_mock(rows_holder["rows"])
        yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        yield client, rows_holder
    finally:
        app.dependency_overrides.clear()


def test_happy_one_inscripcion_returns_one_materia(client_estudiante) -> None:
    """Alumno con 1 inscripción activa recibe 1 fila completa."""
    client, rows_holder = client_estudiante

    materia_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    comision_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    periodo_id = UUID("12345678-1234-1234-1234-123456789abc")
    inscripcion_id = uuid4()

    rows_holder["rows"] = [
        _row(
            materia_id=materia_id,
            materia_codigo="PROG2",
            materia_nombre="Programacion 2",
            comision_id=comision_id,
            comision_codigo="A",
            comision_nombre="A-Manana",
            horario={},
            periodo_id=periodo_id,
            periodo_codigo="2026-S1",
            inscripcion_id=inscripcion_id,
            fecha_inscripcion=date(2026, 3, 20),
        )
    ]

    r = client.get("/api/v1/materias/mias")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] == 1
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["materia_id"] == str(materia_id)
    assert item["codigo"] == "PROG2"
    assert item["nombre"] == "Programacion 2"
    assert item["comision_id"] == str(comision_id)
    assert item["comision_codigo"] == "A"
    assert item["comision_nombre"] == "A-Manana"
    assert item["periodo_id"] == str(periodo_id)
    assert item["periodo_codigo"] == "2026-S1"
    assert item["inscripcion_id"] == str(inscripcion_id)
    assert item["fecha_inscripcion"] == "2026-03-20"
    assert item["horario_resumen"] is None  # JSONB vacio


def test_horario_jsonb_extracts_first_string(client_estudiante) -> None:
    """Si `comisiones.horario` JSONB contiene un string, se promueve a `horario_resumen`."""
    client, rows_holder = client_estudiante

    rows_holder["rows"] = [
        _row(
            materia_id=uuid4(),
            materia_codigo="ALG1",
            materia_nombre="Algoritmos 1",
            comision_id=uuid4(),
            comision_codigo="A",
            comision_nombre="A-Manana",
            horario={"resumen": "Lun/Mie 8-10"},
            periodo_id=uuid4(),
            periodo_codigo="2026-S1",
            inscripcion_id=uuid4(),
            fecha_inscripcion=date(2026, 3, 20),
        )
    ]

    r = client.get("/api/v1/materias/mias")
    assert r.status_code == 200
    item = r.json()["data"][0]
    assert item["horario_resumen"] == "Lun/Mie 8-10"


def test_zero_inscripciones_returns_empty_list_not_404(client_estudiante) -> None:
    """Alumno sin inscripciones recibe `[]`, NO 404 — la home muestra empty state honesto."""
    client, rows_holder = client_estudiante
    rows_holder["rows"] = []

    r = client.get("/api/v1/materias/mias")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


def test_multiple_materias_orden_estable(client_estudiante) -> None:
    """Múltiples inscripciones se devuelven todas, sin paginación.

    El servicio confía en `ORDER BY p.codigo DESC, m.codigo ASC` del SQL.
    Acá solo verificamos que las filas que el mock devuelve llegan completas
    en el response.
    """
    client, rows_holder = client_estudiante

    rows_holder["rows"] = [
        _row(
            materia_id=uuid4(),
            materia_codigo="PROG2",
            materia_nombre="Programacion 2",
            comision_id=uuid4(),
            comision_codigo="A",
            comision_nombre="A-Manana",
            horario={},
            periodo_id=uuid4(),
            periodo_codigo="2026-S1",
            inscripcion_id=uuid4(),
            fecha_inscripcion=date(2026, 3, 20),
        ),
        _row(
            materia_id=uuid4(),
            materia_codigo="REDES1",
            materia_nombre="Redes 1",
            comision_id=uuid4(),
            comision_codigo="B",
            comision_nombre="B-Tarde",
            horario={},
            periodo_id=uuid4(),
            periodo_codigo="2026-S1",
            inscripcion_id=uuid4(),
            fecha_inscripcion=date(2026, 3, 25),
        ),
    ]

    r = client.get("/api/v1/materias/mias")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] == 2
    codigos = [item["codigo"] for item in body["data"]]
    assert codigos == ["PROG2", "REDES1"]


def test_comision_nombre_nullable_passes_through(client_estudiante) -> None:
    """Si `comision.nombre` es NULL en la DB, el response tiene `null` (no string vacío)."""
    client, rows_holder = client_estudiante

    rows_holder["rows"] = [
        _row(
            materia_id=uuid4(),
            materia_codigo="MAT1",
            materia_nombre="Matematica 1",
            comision_id=uuid4(),
            comision_codigo="A",
            comision_nombre=None,  # NULL en DB
            horario={},
            periodo_id=uuid4(),
            periodo_codigo="2026-S1",
            inscripcion_id=uuid4(),
            fecha_inscripcion=date(2026, 3, 20),
        )
    ]

    r = client.get("/api/v1/materias/mias")
    assert r.status_code == 200
    item = r.json()["data"][0]
    assert item["comision_nombre"] is None


def test_endpoint_requires_materia_read_permission(tenant_a_id: UUID) -> None:
    """Un user sin rol que tenga `materia:read` recibe 403.

    El seed agrega `("role:estudiante", "*", "materia:*", "read")` post B.2.
    Un rol arbitrario sin policies cae a 403 via `require_permission`.
    """
    async def _override_user() -> User:
        return User(
            id=uuid4(),
            tenant_id=tenant_a_id,
            email="rando@demo.edu",
            roles=frozenset({"rol_inexistente"}),
            realm=str(tenant_a_id),
        )

    async def _override_db():
        session = _build_session_mock([])
        yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        r = client.get("/api/v1/materias/mias")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
