"""Tests de la verificación de firma del gateway (A0.1).

Mismo enfoque conservador que governance-service (A0.4): la dependency
``require_gateway_auth`` va detrás del flag ``require_gateway_signature``
(default OFF) y corre ADEMÁS de la validación de headers existente.

Cubre el contrato pedido:
  - flag OFF                 → pasa (comportamiento actual, no rompe make)
  - flag ON sin firma        → 401
  - flag ON con firma válida → 200
  - flag ON con service token → 200 (allowlist para callers internos directos)
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from analytics_service import config
from analytics_service.auth import INTERNAL_SERVICE_TOKEN_HEADER
from analytics_service.main import app
from fastapi.testclient import TestClient
from platform_observability import sign_headers

_SECRET = "test-gateway-secret"
_SERVICE_TOKEN = "test-internal-service-token"
_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER = "11111111-1111-1111-1111-111111111111"
_ROLES = "docente"

_BASE_HEADERS = {"X-Tenant-Id": _TENANT, "X-User-Id": _USER}
_RATINGS = {
    "ratings": [
        {"episode_id": "ep1", "rater_a": "delegacion_pasiva", "rater_b": "delegacion_pasiva"},
    ]
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def signature_on() -> Iterator[None]:
    """Prende el flag + configura secreto/token, restaurando al terminar."""
    s = config.settings
    prev = (
        s.require_gateway_signature,
        s.gateway_shared_secret,
        s.internal_service_token,
    )
    s.require_gateway_signature = True
    s.gateway_shared_secret = _SECRET
    s.internal_service_token = _SERVICE_TOKEN
    try:
        yield
    finally:
        (
            s.require_gateway_signature,
            s.gateway_shared_secret,
            s.internal_service_token,
        ) = prev


# ── flag OFF (default) ────────────────────────────────────────────────────


def test_flag_off_pasa_sin_firma(client: TestClient) -> None:
    """Sin el flag, kappa responde 200 solo con los headers de identidad."""
    r = client.post("/api/v1/analytics/kappa", json=_RATINGS, headers=_BASE_HEADERS)
    assert r.status_code == 200


# ── flag ON ────────────────────────────────────────────────────────────────


def test_flag_on_sin_firma_da_401(client: TestClient, signature_on: None) -> None:
    """Con el flag, headers forjados sin firma ni token → 401."""
    r = client.post("/api/v1/analytics/kappa", json=_RATINGS, headers=_BASE_HEADERS)
    assert r.status_code == 401


def test_flag_on_con_firma_valida_da_200(client: TestClient, signature_on: None) -> None:
    """Con el flag, firma HMAC válida del gateway → 200."""
    ts = int(time.time())
    sig = sign_headers(_SECRET, _USER, _TENANT, _ROLES, ts)
    headers = {
        **_BASE_HEADERS,
        "X-User-Roles": _ROLES,
        "X-Gateway-Ts": str(ts),
        "X-Gateway-Signature": sig,
    }
    r = client.post("/api/v1/analytics/kappa", json=_RATINGS, headers=headers)
    assert r.status_code == 200


def test_flag_on_con_firma_invalida_da_401(client: TestClient, signature_on: None) -> None:
    """Firma que no valida contra el secreto → 401."""
    ts = int(time.time())
    headers = {
        **_BASE_HEADERS,
        "X-User-Roles": _ROLES,
        "X-Gateway-Ts": str(ts),
        "X-Gateway-Signature": "deadbeef" * 8,
    }
    r = client.post("/api/v1/analytics/kappa", json=_RATINGS, headers=headers)
    assert r.status_code == 401


def test_flag_on_con_service_token_da_200(client: TestClient, signature_on: None) -> None:
    """Allowlist: X-Internal-Service-Token válido (camino de los make) → 200."""
    headers = {**_BASE_HEADERS, INTERNAL_SERVICE_TOKEN_HEADER: _SERVICE_TOKEN}
    r = client.post("/api/v1/analytics/kappa", json=_RATINGS, headers=headers)
    assert r.status_code == 200


def test_flag_on_export_router_tambien_gateado(client: TestClient, signature_on: None) -> None:
    """El router de export (Caliper/xAPI) también exige procedencia con el flag ON."""
    r = client.get(
        "/api/v1/export/caliper/00000000-0000-0000-0000-000000000123",
        headers=_BASE_HEADERS,
    )
    assert r.status_code == 401


def test_flag_on_health_no_gateado(client: TestClient, signature_on: None) -> None:
    """health NO lleva la verificación: los probes siguen respondiendo sin firma."""
    r = client.get("/health")
    assert r.status_code in (200, 503)
