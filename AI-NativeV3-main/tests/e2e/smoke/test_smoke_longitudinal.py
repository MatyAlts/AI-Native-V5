"""Smoke E2E — path cii_evolution_longitudinal cierra end-to-end con datos del seed.

ADR-042 path 1 reforzado: el seed-3-comisiones garantiza que A1/A2/A3 tienen
>=4 episodios apuntando al mismo template (`NARRATIVE_TEMPLATE_ID`). Este test
ataca el endpoint via api-gateway y verifica que devuelve slope no-null y
n_episodes_total >= 3, sin caer en `insufficient_data` para los estudiantes
narrativos.

Atrapa: regresion del seed (round-robin que deja a estudiantes borderline),
regresion del endpoint longitudinal, regresion del threshold MIN=3 en
`packages/platform-ops/src/platform_ops/cii_longitudinal.py`.

Si este smoke falla, hay regresion en:
- el seed (NARRATIVE_STUDENTS_LONGITUDINAL no se aplico)
- el endpoint /api/v1/analytics/student/{id}/cii-evolution-longitudinal
- el threshold MIN_EPISODES_FOR_LONGITUDINAL en cii_longitudinal.py
"""

from __future__ import annotations

import httpx
import pytest

from _helpers import (  # type: ignore[import-not-found]
    COMISION_A_MANANA,
    STUDENT_A1,
)


@pytest.mark.smoke
def test_longitudinal_devuelve_slope_para_estudiante_narrativo(
    client: httpx.Client, auth_headers
) -> None:
    """ADR-042: A1 (estudiante narrativo) tiene >=4 episodios por template — slope no-null."""
    resp = client.get(
        f"/api/v1/analytics/student/{STUDENT_A1}/cii-evolution-longitudinal",
        params={"comision_id": COMISION_A_MANANA},
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, (
        f"GET cii-evolution-longitudinal fallo: {resp.status_code} {resp.text[:500]}"
    )
    body = resp.json()

    # El response shape es: {student_pseudonym, comision_id, evolution_per_template,
    # n_groups_evaluated, labeler_version, ...}.
    assert body["student_pseudonym"] == STUDENT_A1
    assert body["comision_id"] == COMISION_A_MANANA
    assert "evolution_per_template" in body, body
    assert isinstance(body["evolution_per_template"], list)

    # ADR-042: A1 debe tener >=1 template evaluable (no insufficient_data).
    eligible = [
        t for t in body["evolution_per_template"] if not t.get("insufficient_data")
    ]
    assert len(eligible) >= 1, (
        f"Esperado >=1 template longitudinal-eligible para A1, got body={body}. "
        f"Posible regresion del seed (NARRATIVE_STUDENTS_LONGITUDINAL no aplicado) "
        f"o del threshold MIN_EPISODES_FOR_LONGITUDINAL=3."
    )

    # Slope debe ser numerico (puede ser positivo, negativo, o cero — depende
    # del patron del seed) y n_episodes >= 3.
    first = eligible[0]
    assert first.get("slope") is not None, f"slope null en template eligible: {first}"
    assert first.get("n_episodes", 0) >= 3, (
        f"n_episodes < MIN=3 en template eligible: {first}"
    )


@pytest.mark.smoke
def test_longitudinal_n_groups_evaluated_para_a1(
    client: httpx.Client, auth_headers
) -> None:
    """ADR-042: contador agregado n_groups_evaluated debe ser >=1 para A1."""
    resp = client.get(
        f"/api/v1/analytics/student/{STUDENT_A1}/cii-evolution-longitudinal",
        params={"comision_id": COMISION_A_MANANA},
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("n_groups_evaluated", 0) >= 1, (
        f"A1 debe tener >=1 grupo evaluado post-seed-reforzado. body={body}"
    )
