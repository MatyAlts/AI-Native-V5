"""Tests de endpoints F7: /cohort/{id}/progression y /ab-test-profiles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from analytics_service.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── Progression endpoint ──────────────────────────────────────────────


def test_progression_endpoint_con_cohorte_vacia(client: TestClient) -> None:
    """El stub DataSource devuelve vacío → cohorte vacía."""
    comision_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    r = client.get(
        f"/api/v1/analytics/cohort/{comision_id}/progression",
        headers={"X-Tenant-Id": tenant_id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["n_students"] == 0
    assert data["n_students_with_enough_data"] == 0
    assert data["mejorando"] == 0
    assert data["empeorando"] == 0
    assert data["net_progression_ratio"] == 0.0
    assert data["trajectories"] == []


def test_progression_endpoint_uuid_invalido_422(client: TestClient) -> None:
    r = client.get(
        "/api/v1/analytics/cohort/not-a-uuid/progression",
        headers={"X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert r.status_code == 422


def test_progression_endpoint_sin_tenant_header_401(client: TestClient) -> None:
    """Sin X-Tenant-Id el endpoint rechaza con 401 (no más hardcoded tenant)."""
    comision_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    r = client.get(f"/api/v1/analytics/cohort/{comision_id}/progression")
    assert r.status_code == 401


def test_progression_endpoint_tenant_header_invalido_400(client: TestClient) -> None:
    """X-Tenant-Id no-UUID retorna 400."""
    comision_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    r = client.get(
        f"/api/v1/analytics/cohort/{comision_id}/progression",
        headers={"X-Tenant-Id": "not-a-uuid"},
    )
    assert r.status_code == 400


def test_progression_endpoint_respeta_tenant_distinto(client: TestClient) -> None:
    """El tenant viene del header — distintos tenants reciben respuestas independientes
    (con stub ambos están vacíos, pero ambos pasan auth y devuelven 200)."""
    comision_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    tenant_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    tenant_b = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    r_a = client.get(
        f"/api/v1/analytics/cohort/{comision_id}/progression",
        headers={"X-Tenant-Id": tenant_a},
    )
    r_b = client.get(
        f"/api/v1/analytics/cohort/{comision_id}/progression",
        headers={"X-Tenant-Id": tenant_b},
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200


# ── A/B testing endpoint ──────────────────────────────────────────────


def _ev(seq: int, event_type: str, minute: int, payload: dict | None = None) -> dict:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def _copypaste_events() -> list[dict]:
    """Escenario claro de delegación pasiva."""
    events = [_ev(0, "episodio_abierto", 0)]
    for i, m in enumerate([2, 2, 3, 15, 15, 16, 18, 25, 25, 26]):
        if i % 3 == 0:
            events.append(
                _ev(
                    len(events),
                    "prompt_enviado",
                    m,
                    {"content": "dame la solución", "prompt_kind": "solicitud_directa"},
                )
            )
        elif i % 3 == 1:
            events.append(_ev(len(events), "tutor_respondio", m, {"content": "..."}))
        else:
            events.append(_ev(len(events), "codigo_ejecutado", m))
    return events


_AB_HEADERS = {
    "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "X-User-Id": "11111111-1111-1111-1111-111111111111",
}


def test_ab_endpoint_con_profile_default(client: TestClient) -> None:
    import sys
    from pathlib import Path

    classifier_src = Path(__file__).parent.parent.parent.parent / "classifier-service/src"
    sys.path.insert(0, str(classifier_src))
    from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE

    r = client.post(
        "/api/v1/analytics/ab-test-profiles",
        headers=_AB_HEADERS,
        json={
            "episodes": [
                {
                    "episode_id": f"ep_{i}",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                }
                for i in range(3)
            ],
            "profiles": [DEFAULT_REFERENCE_PROFILE],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["n_episodes"] == 3
    assert len(data["results"]) == 1
    # El profile default detecta correctamente estos copypastes
    assert data["winner_by_kappa"] == DEFAULT_REFERENCE_PROFILE["name"]
    # Predicciones presentes
    for _ep_id, pred in data["results"][0]["predictions"].items():
        assert pred == "delegacion_pasiva"


def test_ab_endpoint_requiere_al_menos_2_episodios(client: TestClient) -> None:
    r = client.post(
        "/api/v1/analytics/ab-test-profiles",
        headers=_AB_HEADERS,
        json={
            "episodes": [
                {
                    "episode_id": "ep_1",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                },
            ],
            "profiles": [{"name": "x", "version": "v1"}],
        },
    )
    assert r.status_code == 400
    assert "2 episodios" in r.json()["detail"]


def test_ab_endpoint_sin_profiles_falla(client: TestClient) -> None:
    r = client.post(
        "/api/v1/analytics/ab-test-profiles",
        headers=_AB_HEADERS,
        json={
            "episodes": [
                {
                    "episode_id": "ep_1",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                },
                {
                    "episode_id": "ep_2",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                },
            ],
            "profiles": [],
        },
    )
    assert r.status_code == 400


def test_ab_endpoint_dos_profiles_reporta_ambos(client: TestClient) -> None:
    import sys
    from pathlib import Path

    classifier_src = Path(__file__).parent.parent.parent.parent / "classifier-service/src"
    sys.path.insert(0, str(classifier_src))
    from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE

    profile_a = dict(DEFAULT_REFERENCE_PROFILE)
    profile_a["name"] = "profile_a"
    profile_b = dict(DEFAULT_REFERENCE_PROFILE)
    profile_b["name"] = "profile_b"

    r = client.post(
        "/api/v1/analytics/ab-test-profiles",
        headers=_AB_HEADERS,
        json={
            "episodes": [
                {
                    "episode_id": f"ep_{i}",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                }
                for i in range(3)
            ],
            "profiles": [profile_a, profile_b],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["results"]) == 2
    # Ambos profiles son idénticos internamente → mismo kappa
    kappas = {r["kappa"] for r in data["results"]}
    assert len(kappas) == 1  # mismo kappa para los dos


# ── HU-088 audit trail ────────────────────────────────────────────────


def test_ab_endpoint_emite_audit_log_estructurado(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """HU-088: el A/B testing deja trace estructurado vía structlog/stdlib
    logging (no se persiste en tabla `audit_log` por decisión de diseño —
    ver entrada HU-088 en BUGS-PILOTO.md). El log debe incluir tenant_id,
    user_id, n_episodes/profiles y winner para auditabilidad académica.
    """
    import logging
    import sys
    from pathlib import Path

    classifier_src = Path(__file__).parent.parent.parent.parent / "classifier-service/src"
    sys.path.insert(0, str(classifier_src))
    from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE

    with caplog.at_level(logging.INFO, logger="analytics_service.routes.analytics"):
        r = client.post(
            "/api/v1/analytics/ab-test-profiles",
            headers=_AB_HEADERS,
            json={
                "episodes": [
                    {
                        "episode_id": f"ep_{i}",
                        "events": _copypaste_events(),
                        "human_label": "delegacion_pasiva",
                    }
                    for i in range(3)
                ],
                "profiles": [DEFAULT_REFERENCE_PROFILE],
            },
        )
    assert r.status_code == 200

    audit_lines = [
        rec for rec in caplog.records if "ab_test_profiles_completed" in rec.getMessage()
    ]
    assert len(audit_lines) == 1, f"esperaba 1 audit log, obtuve {len(audit_lines)}"

    msg = audit_lines[0].getMessage()
    assert _AB_HEADERS["X-Tenant-Id"] in msg
    assert _AB_HEADERS["X-User-Id"] in msg
    assert "n_episodes_compared=3" in msg
    assert "n_profiles_compared=1" in msg
    assert f"winner_profile_name={DEFAULT_REFERENCE_PROFILE['name']}" in msg
    assert "classifier_config_hash=" in msg


def test_ab_endpoint_sin_tenant_header_401(client: TestClient) -> None:
    """HU-088 + BUG-21 pattern: sin `X-Tenant-Id` el endpoint rechaza con 401."""
    r = client.post(
        "/api/v1/analytics/ab-test-profiles",
        headers={"X-User-Id": _AB_HEADERS["X-User-Id"]},
        json={
            "episodes": [
                {
                    "episode_id": f"ep_{i}",
                    "events": _copypaste_events(),
                    "human_label": "delegacion_pasiva",
                }
                for i in range(2)
            ],
            "profiles": [{"name": "x", "version": "v1"}],
        },
    )
    assert r.status_code == 401
