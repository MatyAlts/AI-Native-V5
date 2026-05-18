"""Smoke #4 — auditoría CTR vía alias /api/v1/audit/* (ADR-031).

Atrapa específicamente el ADR-031 D.4: el `audit_router` registra
`get_episode` y `verify_episode_chain` apuntando a las mismas funciones del
router legacy del ctr-service. Si alguien duplica los handlers o cambia el
alias por error, este test falla.

Verifica:
  1. POST /api/v1/audit/episodes/{id}/verify (alias) → 200 con valid:true
  2. POST /api/v1/episodes/{id}/verify directo al :8007 → 200 con la MISMA
     respuesta (mismo handler, ADR-031)
  3. GET /api/v1/audit/episodes/{id} → devuelve EpisodeWithEvents con
     events_count y last_chain_hash
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.smoke
def test_audit_verify_via_gateway_returns_valid(
    client: httpx.Client, auth_headers, seeded_episode_id: str
) -> None:
    """POST /api/v1/audit/episodes/{id}/verify (alias) debe devolver valid:true.

    El seed garantiza que este episodio tiene 5 events íntegros. Si la
    cadena se rompió (corrupción o bug en hashing), `valid:false` con
    `failing_seq` detallando dónde diverge — eso es FAIL.
    """
    resp = client.post(
        f"/api/v1/audit/episodes/{seeded_episode_id}/verify",
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, (
        f"POST audit/verify alias deberia OK. "
        f"status={resp.status_code} body={resp.text[:400]}"
    )
    body = resp.json()
    assert body["valid"] is True, (
        f"Cadena criptografica del episodio seed deberia ser íntegra. "
        f"failing_seq={body.get('failing_seq')} message={body.get('message')}"
    )
    assert body["events_count"] >= 5, (
        f"esperaba >=5 eventos en el seeded_episode, got {body['events_count']}"
    )
    assert body["integrity_compromised"] is False


@pytest.mark.smoke
def test_audit_verify_alias_matches_legacy(seeded_episode_id: str) -> None:
    """ADR-031 D.4: el alias /api/v1/audit/* y el legacy /api/v1/episodes/* del
    ctr-service apuntan al MISMO handler. Sus responses deben ser idénticas
    (mismo episodio, mismas verificaciones).

    Pegamos directo al ctr-service (:8007) para el legacy — `/api/v1/episodes`
    en el gateway está tomado por el tutor-service.
    """
    headers = {
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "X-User-Email": "docente@demo-uni.edu",
        "X-User-Roles": "docente",
    }

    # Alias via gateway → ctr-service
    via_alias = httpx.post(
        f"http://127.0.0.1:8000/api/v1/audit/episodes/{seeded_episode_id}/verify",
        headers=headers,
        timeout=5.0,
    )
    # Legacy directo al ctr-service
    via_legacy = httpx.post(
        f"http://127.0.0.1:8007/api/v1/episodes/{seeded_episode_id}/verify",
        headers=headers,
        timeout=5.0,
    )

    assert via_alias.status_code == 200, f"alias falló: {via_alias.text[:200]}"
    assert via_legacy.status_code == 200, f"legacy falló: {via_legacy.text[:200]}"

    # Comparamos campos clave, no el dict entero (algunos campos volátiles
    # como timestamps o request_id pueden diferir).
    a = via_alias.json()
    le = via_legacy.json()
    for field in ("episode_id", "valid", "events_count", "failing_seq", "integrity_compromised"):
        assert a[field] == le[field], (
            f"Campo {field!r} difiere entre alias y legacy. "
            f"alias={a[field]!r} legacy={le[field]!r}"
        )


@pytest.mark.smoke
def test_audit_get_episode_returns_events(
    client: httpx.Client, auth_headers, seeded_episode_id: str
) -> None:
    """GET /api/v1/audit/episodes/{id} → EpisodeWithEvents con events list."""
    resp = client.get(
        f"/api/v1/audit/episodes/{seeded_episode_id}",
        headers=auth_headers("docente"),
    )
    assert resp.status_code == 200, f"audit get_episode failed: {resp.text[:300]}"
    body = resp.json()
    assert body["id"] == seeded_episode_id
    assert body["estado"] == "closed"
    assert body["integrity_compromised"] is False
    assert body["events_count"] >= 5
    assert isinstance(body.get("events"), list)
    assert len(body["events"]) == body["events_count"]
    # last_chain_hash debe ser un SHA-256 hex válido (64 chars hex).
    last_chain = body["last_chain_hash"]
    assert isinstance(last_chain, str) and len(last_chain) == 64
    int(last_chain, 16)  # raises si no es hex
