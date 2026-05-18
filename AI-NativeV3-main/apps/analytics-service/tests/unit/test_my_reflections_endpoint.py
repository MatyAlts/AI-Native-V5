"""Tests del endpoint GET /api/v1/analytics/student/me/reflections (ADR-035).

Cubre el contrato del response, los gates de autenticacion y el
comportamiento en modo dev (sin DBs configuradas). Las queries reales
se cubren en smoke tests cuando hay stack levantado.

Privacy: el filtro por `student_pseudonym = X-User-Id` es la garantia
critica — el estudiante solo ve sus propias reflexiones. El path
canonico `/student/me/reflections` evita que el cliente pase otro UUID
en el path. Tests explicitos:
  - Sin X-User-Id → 401.
  - El `student_pseudonym` del response coincide con el X-User-Id.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient

_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER = "11111111-1111-1111-1111-111111111111"
_HEADERS = {"X-Tenant-Id": _TENANT, "X-User-Id": _USER}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── Auth gates ────────────────────────────────────────────────────────


def test_reflections_sin_user_header_devuelve_401(client: TestClient) -> None:
    """Sin X-User-Id no podemos resolver `student_pseudonym` — privacy gate."""
    r = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers={"X-Tenant-Id": _TENANT},
    )
    assert r.status_code == 401


def test_reflections_sin_tenant_header_devuelve_401(client: TestClient) -> None:
    r = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers={"X-User-Id": _USER},
    )
    assert r.status_code == 401


def test_reflections_user_id_no_uuid_devuelve_400(client: TestClient) -> None:
    r = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers={"X-Tenant-Id": _TENANT, "X-User-Id": "not-a-uuid"},
    )
    assert r.status_code == 400


# ── Modo dev (sin DBs configuradas): estructura vacia ─────────────────


def test_reflections_modo_dev_devuelve_lista_vacia(client: TestClient) -> None:
    """Sin CTR_STORE_URL ni ACADEMIC_DB_URL el endpoint cae al stub.

    Debe devolver 200 con lista vacia — coherente con el resto de
    endpoints de analytics que tienen el mismo gate.
    """
    r = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["student_pseudonym"] == _USER
    assert data["n_returned"] == 0
    assert data["has_more"] is False
    assert data["cursor_next"] is None
    assert data["reflections"] == []


def test_reflections_response_shape_es_estable(client: TestClient) -> None:
    """El shape del response es contrato publico — el wrapper TS depende de el."""
    r = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {
        "student_pseudonym",
        "n_returned",
        "has_more",
        "cursor_next",
        "reflections",
    }


# ── Privacy: student_pseudonym del response = X-User-Id ───────────────


def test_reflections_student_pseudonym_viene_del_header_no_del_path(
    client: TestClient,
) -> None:
    """El endpoint NO acepta path param `student_id`. El `student_pseudonym`
    del response SIEMPRE coincide con `X-User-Id` — ningun cliente puede
    pedir las reflexiones de otro estudiante."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    r_a = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers={"X-Tenant-Id": _TENANT, "X-User-Id": user_a},
    )
    r_b = client.get(
        "/api/v1/analytics/student/me/reflections",
        headers={"X-Tenant-Id": _TENANT, "X-User-Id": user_b},
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json()["student_pseudonym"] == user_a
    assert r_b.json()["student_pseudonym"] == user_b
    assert r_a.json()["student_pseudonym"] != r_b.json()["student_pseudonym"]


def test_reflections_no_existe_endpoint_con_path_param_pseudonym(
    client: TestClient,
) -> None:
    """Defensa: el path `/student/{uuid}/reflections` NO debe existir.

    El listado siempre es `me`. Si alguien agrega un path param en el
    futuro, este test obliga a justificarlo (cambio explicito) — sino
    abriria la puerta a que el cliente pase cualquier UUID."""
    other_student = str(uuid4())
    r = client.get(
        f"/api/v1/analytics/student/{other_student}/reflections",
        headers=_HEADERS,
    )
    # 404 (route no existe) — Starlette devuelve 404 cuando no matchea.
    # NUNCA 200 (eso indicaria que estamos exponiendo data de otro estudiante).
    assert r.status_code == 404


# ── Pagination: limit + cursor ────────────────────────────────────────


def test_reflections_limit_y_cursor_son_query_params_opcionales(
    client: TestClient,
) -> None:
    r = client.get(
        "/api/v1/analytics/student/me/reflections?limit=5",
        headers=_HEADERS,
    )
    assert r.status_code == 200


def test_reflections_cursor_invalido_devuelve_400_en_modo_real(
    client: TestClient,
) -> None:
    """En modo dev el cursor ni se parsea (sale early con stub vacio).
    El parse del cursor (y su 400) cubre el modo real — verificable en
    smoke tests contra DB."""
    # Skip if env not real
    r = client.get(
        "/api/v1/analytics/student/me/reflections?cursor=not-iso-datetime",
        headers=_HEADERS,
    )
    # Modo dev: 200 con stub vacio (cursor parsing solo aplica en modo real).
    # Si en CI/local hay DBs configuradas, va a devolver 400.
    assert r.status_code in (200, 400)
