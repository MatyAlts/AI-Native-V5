"""Smoke #5 — endpoints de analytics consumidos por web-teacher.

Atrapa: cambios en headers requeridos (analytics requires X-Tenant-Id +
X-User-Id), regresiones en privacy gate `MIN_STUDENTS_FOR_QUARTILES=5`,
breakage en CII longitudinal por template, breakage de kappa cómputo.

Estos endpoints son la columna vertebral del web-teacher. Si rompen, los
docentes ven dashboards vacíos y pierden trust en el piloto.
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.smoke
def test_kappa_endpoint_computes_valid_kappa(
    client: httpx.Client, auth_headers
) -> None:
    """POST /api/v1/analytics/kappa con 5 ratings concordantes → κ alto."""
    payload = {
        "ratings": [
            {
                "episode_id": "e1",
                "rater_a": "apropiacion_reflexiva",
                "rater_b": "apropiacion_reflexiva",
            },
            {
                "episode_id": "e2",
                "rater_a": "delegacion_pasiva",
                "rater_b": "delegacion_pasiva",
            },
            {
                "episode_id": "e3",
                "rater_a": "apropiacion_superficial",
                "rater_b": "apropiacion_superficial",
            },
            {
                "episode_id": "e4",
                "rater_a": "apropiacion_reflexiva",
                "rater_b": "apropiacion_reflexiva",
            },
            {
                "episode_id": "e5",
                "rater_a": "delegacion_pasiva",
                "rater_b": "delegacion_pasiva",
            },
        ]
    }
    resp = client.post(
        "/api/v1/analytics/kappa", json=payload, headers=auth_headers("docente")
    )
    assert resp.status_code == 200, (
        f"POST kappa con headers docente debería OK. "
        f"status={resp.status_code} body={resp.text[:400]}"
    )
    body = resp.json()
    assert body["n_episodes"] == 5
    # 5 ratings idénticos → κ=1.0 perfecto
    assert body["kappa"] == 1.0, f"esperado κ=1.0 con ratings idénticos, got {body['kappa']}"
    # Interpretation segun Landis & Koch — el valor exacto es localizado
    # ("casi perfecto" en es-AR). Lo importante es que no sea vacio.
    assert isinstance(body["interpretation"], str) and body["interpretation"]
    assert "confusion_matrix" in body
    assert "per_class_agreement" in body


@pytest.mark.smoke
def test_kappa_requires_tenant_header(client: httpx.Client) -> None:
    """Sin X-Tenant-Id → 401/403 (no debe procesar request).

    Atrapa: si alguien quita el `Depends(get_tenant_id)` del endpoint, este
    test falla. Sin enforce de headers se viola el invariante "api-gateway
    es el único source of truth de identidad" — los headers internos los
    inyecta el gateway autoritativamente.
    """
    payload = {
        "ratings": [
            {
                "episode_id": "e1",
                "rater_a": "apropiacion_reflexiva",
                "rater_b": "apropiacion_reflexiva",
            }
        ]
    }
    resp = client.post("/api/v1/analytics/kappa", json=payload)
    # El gateway en dev_trust_headers requiere X-Tenant-Id + X-User-Id, sin
    # esos cae a 401. Sería diferente si jwt_validator estuviera activo.
    assert resp.status_code in (401, 403, 422), (
        f"sin headers de auth no debería procesar kappa. status={resp.status_code}"
    )


@pytest.mark.smoke
def test_cii_evolution_longitudinal_for_seeded_student(
    client: httpx.Client, auth_headers, student_id: str, comision_id: str
) -> None:
    """ADR-018, RN-130: slope per-template del student del seed.

    El estudiante b1b1b1b1-...-001 tiene 6 episodios del seed sobre 2
    templates → slope debe estar definido.
    """
    resp = client.get(
        f"/api/v1/analytics/student/{student_id}/cii-evolution-longitudinal",
        params={"comision_id": comision_id},
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, (
        f"GET cii-evolution-longitudinal falló: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["student_pseudonym"] == student_id
    assert body["comision_id"] == comision_id
    # En el seed-3-comisiones, este student tiene >= 1 template evaluable
    assert body["n_groups_evaluated"] >= 1, (
        f"esperaba al menos 1 template evaluable para este student. body={body}"
    )
    assert "evolution_per_template" in body
    assert isinstance(body["evolution_per_template"], list)
    assert "labeler_version" in body  # versionado declarable


@pytest.mark.smoke
def test_cii_quartiles_respects_privacy_gate(
    client: httpx.Client, auth_headers, comision_id: str
) -> None:
    """ADR-022: cuartiles requieren N≥5 (k-anonymity).

    El seed tiene 6 estudiantes en A-Mañana → al menos 5 evaluables → cuartiles
    visibles. Si el privacy gate baja a <5 por error, este test sigue pasando
    (la cohorte es 6) pero el test_cii_alerts_endpoint cubre el otro lado.
    """
    resp = client.get(
        f"/api/v1/analytics/cohort/{comision_id}/cii-quartiles",
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, f"GET cii-quartiles failed: {resp.text[:300]}"
    body = resp.json()
    assert body["min_students_for_quartiles"] == 5, (
        f"privacy gate cambió: esperado 5, got {body['min_students_for_quartiles']}. "
        f"Modificar este umbral viola RN-131 sin un ADR."
    )
    if body["insufficient_data"] is False:
        # Cuartiles deben estar presentes
        for k in ("q1", "median", "q3", "min", "max"):
            assert k in body, f"falta {k} en cuartiles"
        assert body["q1"] <= body["median"] <= body["q3"], "cuartiles no monotónicos"


@pytest.mark.smoke
def test_alerts_endpoint_returns_quartile(
    client: httpx.Client, auth_headers, student_id: str, comision_id: str
) -> None:
    """ADR-022 (RN-131): alertas predictivas — z-score vs cohorte, no ML."""
    resp = client.get(
        f"/api/v1/analytics/student/{student_id}/alerts",
        params={"comision_id": comision_id},
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, f"GET alerts failed: {resp.text[:300]}"
    body = resp.json()
    assert body["student_pseudonym"] == student_id
    # quartile o insufficient_data — uno u otro debe estar
    assert "quartile" in body or body.get("insufficient_data") is True, body
