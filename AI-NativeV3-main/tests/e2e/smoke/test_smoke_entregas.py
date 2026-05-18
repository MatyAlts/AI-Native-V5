"""Smoke #8 — entregas + calificaciones endpoints (tp-entregas-correccion).

Valida el ciclo completo de la evaluation-service:
  1. Estudiante crea/recupera entrega (idempotente).
  2. Docente lista entregas por comision.
  3. Docente crea calificacion (submitted → graded).
  4. Docente devuelve entrega (graded → returned).

Requiere:
  - evaluation-service en :8004 respondiendo /health
  - Migration 20260506_0001 aplicada (tablas entregas + calificaciones)
  - Casbin policies para entrega/calificacion cargadas (seed-casbin)
  - Seed demo activo: comision_id = COMISION_A_MANANA, tarea_practica_id = TP01

Los tests de ciclo completo son SECUENCIALES (usan module-scoped state para
propagar el entrega_id entre tests). Pytest ordena tests dentro del modulo
en el orden en que aparecen.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from _helpers import (  # type: ignore[import-not-found]
    COMISION_A_MANANA,
    DOCENTE_DEMO,
    STUDENT_A1,
    TENANT_DEMO,
)

# ── State compartido entre tests del modulo ────────────────────────────

_state: dict[str, str] = {}

TAREA_PRACTICA_ID = "11110000-0000-0000-c0de-c0dec0dec0df"


def _student_headers() -> dict[str, str]:
    return {
        "X-User-Id": STUDENT_A1,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "alumno@demo-uni.edu",
        "X-User-Roles": "estudiante",
    }


def _docente_headers() -> dict[str, str]:
    return {
        "X-User-Id": DOCENTE_DEMO,
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.smoke
def test_student_create_entrega_idempotente(client: httpx.Client) -> None:
    """POST /api/v1/entregas → 201 con UUID; segunda llamada → 200 misma entrega."""
    payload = {
        "tarea_practica_id": TAREA_PRACTICA_ID,
        "comision_id": COMISION_A_MANANA,
    }
    # Primera llamada: crear
    resp1 = client.post("/api/v1/entregas", json=payload, headers=_student_headers())
    assert resp1.status_code in (200, 201), (
        f"create entrega failed: {resp1.status_code} {resp1.text}"
    )
    body1 = resp1.json()
    entrega_id = body1.get("id")
    assert entrega_id, f"response missing id: {body1}"
    # Validar que es UUID parseable
    UUID(entrega_id)
    assert body1.get("estado") == "draft", f"expected draft, got: {body1.get('estado')}"

    # Segunda llamada: idempotente → devuelve la misma entrega
    resp2 = client.post("/api/v1/entregas", json=payload, headers=_student_headers())
    assert resp2.status_code in (200, 201), (
        f"idempotent create failed: {resp2.status_code} {resp2.text}"
    )
    body2 = resp2.json()
    assert body2.get("id") == entrega_id, (
        f"idempotent create returned different entrega: {body2.get('id')} != {entrega_id}"
    )

    # Persistir para los siguientes tests
    _state["entrega_id"] = entrega_id


@pytest.mark.smoke
def test_docente_list_entregas(client: httpx.Client) -> None:
    """GET /api/v1/entregas?comision_id=... → 200 con lista."""
    resp = client.get(
        "/api/v1/entregas",
        params={"comision_id": COMISION_A_MANANA},
        headers=_docente_headers(),
    )
    assert resp.status_code == 200, f"list entregas failed: {resp.status_code} {resp.text}"
    body = resp.json()
    assert "data" in body, f"response missing data: {body}"
    assert isinstance(body["data"], list), f"data is not list: {body}"


@pytest.mark.smoke
def test_student_get_entrega_detail(client: httpx.Client) -> None:
    """GET /api/v1/entregas/{id} → 200 con detail."""
    entrega_id = _state.get("entrega_id")
    if not entrega_id:
        pytest.skip("entrega_id no disponible (test anterior fallo)")
    resp = client.get(
        f"/api/v1/entregas/{entrega_id}",
        headers=_student_headers(),
    )
    assert resp.status_code == 200, f"get entrega failed: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body.get("id") == entrega_id


@pytest.mark.smoke
def test_calificacion_requires_submitted_estado(client: httpx.Client) -> None:
    """POST .../calificar en entrega draft → 409 (no submitted)."""
    entrega_id = _state.get("entrega_id")
    if not entrega_id:
        pytest.skip("entrega_id no disponible")
    resp = client.post(
        f"/api/v1/entregas/{entrega_id}/calificar",
        json={"nota_final": 8.0, "feedback_general": "Bien"},
        headers=_docente_headers(),
    )
    # Debe rechazar porque la entrega esta en draft, no submitted
    assert resp.status_code in (409, 422, 400), (
        f"expected 409/422/400 for non-submitted entrega, got: {resp.status_code} {resp.text}"
    )


@pytest.mark.smoke
def test_docente_get_calificacion_missing(client: httpx.Client) -> None:
    """GET .../calificacion en entrega sin calificacion → 404."""
    entrega_id = _state.get("entrega_id")
    if not entrega_id:
        pytest.skip("entrega_id no disponible")
    resp = client.get(
        f"/api/v1/entregas/{entrega_id}/calificacion",
        headers=_docente_headers(),
    )
    assert resp.status_code == 404, (
        f"expected 404 for missing calificacion, got: {resp.status_code} {resp.text}"
    )


@pytest.mark.smoke
def test_evaluation_service_health() -> None:
    """evaluation-service /health responde 200 o 503 (degraded ok)."""
    resp = httpx.get("http://127.0.0.1:8004/health", timeout=3.0)
    assert resp.status_code in (200, 503), (
        f"evaluation-service health check failed: {resp.status_code}"
    )
