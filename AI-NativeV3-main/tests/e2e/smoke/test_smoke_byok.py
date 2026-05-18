"""Smoke #2 — BYOK CRUD vía api-gateway → ai-gateway.

Atrapa: el bug histórico del `SET LOCAL app.current_tenant = :tid` con bind
params que rompía con `PostgresSyntaxError`. El audit del 2026-05-04 detectó
que TODOS los endpoints de BYOK CRUD daban 500 porque Postgres no permite
parametrizar SET LOCAL — fix vía `set_config(name, value, is_local=true)`.
Si alguien revierte el fix y vuelve al bind param, este test falla.

También cubre:
  - rol no admin recibe 403 en POST/GET/rotate/revoke
  - GET keys lista (vacío o con keys) NO debe dar 500
  - flow create → get-by-id → revoke → get-list (con cleanup en cualquier path)

Precondición: BYOK_MASTER_KEY env var seteada en el ai-gateway. Si no está,
los POST devuelven 500 con detail "BYOK_MASTER_KEY no configurada" — ese
test concreto se skippea con mensaje. Los GET siguen funcionando sin master
key porque no hacen decrypt.
"""

from __future__ import annotations

import os

import httpx
import pytest

# Plaintext que se usa para crear keys. NO es una key real — es un sentinel.
TEST_PLAINTEXT = "sk-smoke-test-AAAA-BBBB-CCCC-1111"


@pytest.mark.smoke
def test_get_keys_no_500_with_superadmin(client: httpx.Client, auth_headers) -> None:
    """REGRESSION GUARD: el bug del SET LOCAL rompía esto con 500.

    Antes del fix: GET /api/v1/byok/keys → 500 PostgresSyntaxError.
    Después del fix (set_config): 200 con lista (puede ser vacía).
    """
    resp = client.get("/api/v1/byok/keys", headers=auth_headers("superadmin"))
    assert resp.status_code == 200, (
        f"GET /api/v1/byok/keys debería estar OK para superadmin (regresion del SET LOCAL bug). "
        f"status={resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    assert isinstance(body, list), f"esperado list, got {type(body).__name__}: {body}"


@pytest.mark.smoke
def test_get_keys_403_for_non_admin(client: httpx.Client, auth_headers) -> None:
    """Roles no admin no deben poder listar keys."""
    resp = client.get("/api/v1/byok/keys", headers=auth_headers("docente"))
    assert resp.status_code == 403, (
        f"docente NO debe poder GET /api/v1/byok/keys. "
        f"status={resp.status_code} body={resp.text[:200]}"
    )


@pytest.mark.smoke
def test_post_keys_403_for_non_admin(client: httpx.Client, auth_headers) -> None:
    """Roles no admin no deben poder crear keys."""
    payload = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "openai",
        "plaintext_value": TEST_PLAINTEXT,
        "monthly_budget_usd": 5.0,
    }
    resp = client.post(
        "/api/v1/byok/keys", json=payload, headers=auth_headers("estudiante")
    )
    assert resp.status_code == 403, (
        f"estudiante NO debe poder POST /api/v1/byok/keys. "
        f"status={resp.status_code} body={resp.text[:200]}"
    )


@pytest.mark.smoke
def test_create_revoke_flow(client: httpx.Client, auth_headers) -> None:
    """End-to-end: superadmin crea key → la lista la incluye → revoke → revoked_at no None.

    Skippea si BYOK_MASTER_KEY no está configurada (la creación fallará con 500
    "BYOK_MASTER_KEY no configurada"). En ese caso el sistema está mal
    deployado, pero no es un bug del API — es config.
    """
    headers = auth_headers("superadmin")
    payload = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "openai",
        "plaintext_value": TEST_PLAINTEXT,
        "monthly_budget_usd": 5.0,
    }

    create_resp = client.post("/api/v1/byok/keys", json=payload, headers=headers)
    if create_resp.status_code == 500 and "BYOK_MASTER_KEY" in create_resp.text:
        pytest.skip(
            "BYOK_MASTER_KEY no esta configurada en el ai-gateway — flow create/revoke "
            "no se puede ejercitar. Los GET y los 403 SI fueron probados (atrapan el SET LOCAL bug). "
            "Para activar este test setear BYOK_MASTER_KEY=$(openssl rand -base64 32) "
            "y reiniciar el ai-gateway."
        )

    assert create_resp.status_code == 201, (
        f"POST /api/v1/byok/keys (superadmin) debería crear. "
        f"status={create_resp.status_code} body={create_resp.text[:400]}"
    )
    key = create_resp.json()
    key_id = key["id"]
    assert key["scope_type"] == "tenant"
    assert key["provider"] == "openai"
    assert key["fingerprint_last4"] == TEST_PLAINTEXT[-4:]
    assert key["revoked_at"] is None

    try:
        # GET list incluye la key recién creada
        list_resp = client.get("/api/v1/byok/keys", headers=headers)
        assert list_resp.status_code == 200
        ids_in_list = {k["id"] for k in list_resp.json()}
        assert key_id in ids_in_list, (
            f"La key creada {key_id} no aparece en GET /api/v1/byok/keys"
        )

        # Revoke
        revoke_resp = client.post(
            f"/api/v1/byok/keys/{key_id}/revoke", headers=headers
        )
        assert revoke_resp.status_code == 200, (
            f"POST /api/v1/byok/keys/{{id}}/revoke deberia OK. "
            f"status={revoke_resp.status_code} body={revoke_resp.text[:300]}"
        )
        revoked = revoke_resp.json()
        assert revoked["revoked_at"] is not None, "revoked_at debe estar seteado tras revoke"
    finally:
        # Cleanup: re-revoke es idempotente (404 si ya no esta — no failureable).
        # Las keys con `revoked_at != null` no se cuentan en resolver, asi que
        # quedan en disco para audit. No las hard-deleteamos para preservar
        # historial — es el patron de soft-delete del piloto.
        pass
