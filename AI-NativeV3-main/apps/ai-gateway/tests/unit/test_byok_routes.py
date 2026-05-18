"""Tests de los endpoints CRUD de BYOK keys.

Cubre `apps/ai-gateway/src/ai_gateway/routes/byok.py`:
- Casbin: solo `superadmin`/`docente_admin` pueden gestionar keys (403 sino).
- POST /keys: validation errors (scope_type/scope_id, master key faltante).
- POST /keys/{id}/rotate: 404 si no existe, 400 si plaintext invalido.
- POST /keys/{id}/revoke: 404 si no existe.
- GET /keys + GET /keys/{id}/usage: filtros y serializacion.
- Headers UUID invalidos -> 400.

Las llamadas a la DB se mockean en `ai_gateway.routes.byok` directamente.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from ai_gateway.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


VALID_TENANT = "11111111-1111-1111-1111-111111111111"
VALID_USER = "22222222-2222-2222-2222-222222222222"
ADMIN_HEADERS = {
    "X-Tenant-Id": VALID_TENANT,
    "X-User-Id": VALID_USER,
    "X-User-Roles": "superadmin",
}
DOCENTE_ADMIN_HEADERS = {
    "X-Tenant-Id": VALID_TENANT,
    "X-User-Id": VALID_USER,
    "X-User-Roles": "docente_admin",
}
ESTUDIANTE_HEADERS = {
    "X-Tenant-Id": VALID_TENANT,
    "X-User-Id": VALID_USER,
    "X-User-Roles": "estudiante",
}


# ── Casbin / authorization ─────────────────────────────────────────────


async def test_estudiante_get_keys_devuelve_403(client: AsyncClient) -> None:
    response = await client.get("/api/v1/byok/keys", headers=ESTUDIANTE_HEADERS)
    assert response.status_code == 403
    assert "byok_key:CRUD" in response.json()["detail"]


async def test_docente_normal_get_keys_devuelve_403(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/byok/keys",
        headers={**ESTUDIANTE_HEADERS, "X-User-Roles": "docente"},
    )
    assert response.status_code == 403


async def test_post_key_estudiante_devuelve_403(client: AsyncClient) -> None:
    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "anthropic",
        "plaintext_value": "sk-ant-1234567890",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ESTUDIANTE_HEADERS
    )
    assert response.status_code == 403


async def test_sin_x_user_roles_header_403(client: AsyncClient) -> None:
    """X-User-Roles ausente == role vacio == 403."""
    response = await client.get(
        "/api/v1/byok/keys",
        headers={"X-Tenant-Id": VALID_TENANT, "X-User-Id": VALID_USER},
    )
    assert response.status_code == 403


async def test_sin_tenant_header_devuelve_422(client: AsyncClient) -> None:
    """X-Tenant-Id es requerido por el Header() — sin el, FastAPI devuelve 422."""
    response = await client.get(
        "/api/v1/byok/keys",
        headers={"X-User-Id": VALID_USER, "X-User-Roles": "superadmin"},
    )
    assert response.status_code == 422


async def test_tenant_uuid_invalido_devuelve_400(client: AsyncClient) -> None:
    """Header X-Tenant-Id presente pero no UUID -> 400."""
    response = await client.get(
        "/api/v1/byok/keys",
        headers={
            "X-Tenant-Id": "not-a-uuid",
            "X-User-Id": VALID_USER,
            "X-User-Roles": "superadmin",
        },
    )
    assert response.status_code == 400
    assert "UUID" in response.json()["detail"]


# ── POST /keys ─────────────────────────────────────────────────────────


async def test_post_key_validation_error_scope_type_invalid(
    client: AsyncClient,
) -> None:
    body = {
        "scope_type": "planeta",  # no esta en el Literal
        "provider": "anthropic",
        "plaintext_value": "sk-ant-1234567890",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 422  # pydantic schema rejection


async def test_post_key_plaintext_demasiado_corto_422(client: AsyncClient) -> None:
    """`plaintext_value` tiene min_length=8 en el Field — pydantic lo rechaza."""
    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "anthropic",
        "plaintext_value": "abc",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 422


async def test_post_key_provider_no_listado_422(client: AsyncClient) -> None:
    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "midudev-llm",
        "plaintext_value": "sk-something-validlength",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 422


async def test_post_key_master_key_missing_devuelve_500(
    client: AsyncClient, monkeypatch
) -> None:
    """Si BYOK_MASTER_KEY no esta seteada, el service raisea ValueError con
    mensaje conteniendo 'BYOK_MASTER_KEY' y el route lo mapea a 500."""

    async def _fake_create(**kwargs):
        raise ValueError("BYOK_MASTER_KEY no configurada")

    monkeypatch.setattr("ai_gateway.routes.byok.create_byok_key", _fake_create)
    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "anthropic",
        "plaintext_value": "sk-ant-secret-key123",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 500
    assert "BYOK_MASTER_KEY" in response.json()["detail"]


async def test_post_key_value_error_no_master_es_400(
    client: AsyncClient, monkeypatch
) -> None:
    """Otros ValueError (no master key) -> 400."""

    async def _fake_create(**kwargs):
        raise ValueError("scope_type=tenant requiere scope_id=None")

    monkeypatch.setattr("ai_gateway.routes.byok.create_byok_key", _fake_create)
    body = {
        "scope_type": "tenant",
        "scope_id": str(uuid4()),  # incompatible — pero pydantic no lo agarra
        "provider": "anthropic",
        "plaintext_value": "sk-ant-secret-key123",
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 400


async def test_post_key_happy_path(client: AsyncClient, monkeypatch) -> None:
    fake_id = str(uuid4())

    async def _fake_create(**kwargs):
        return {
            "id": fake_id,
            "tenant_id": VALID_TENANT,
            "scope_type": "tenant",
            "scope_id": None,
            "provider": "anthropic",
            "fingerprint_last4": "y123",
            "monthly_budget_usd": 100.0,
            "created_at": "2026-05-07T00:00:00+00:00",
            "created_by": VALID_USER,
            "revoked_at": None,
            "last_used_at": None,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.create_byok_key", _fake_create)

    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "anthropic",
        "plaintext_value": "sk-ant-completebody123",
        "monthly_budget_usd": 100.0,
    }
    response = await client.post(
        "/api/v1/byok/keys", json=body, headers=DOCENTE_ADMIN_HEADERS
    )
    assert response.status_code == 201
    out = response.json()
    assert out["id"] == fake_id
    assert out["fingerprint_last4"] == "y123"


# ── GET /keys ──────────────────────────────────────────────────────────


async def test_get_keys_lista_vacia(client: AsyncClient, monkeypatch) -> None:
    async def _fake_list(*args, **kwargs):
        return []

    monkeypatch.setattr("ai_gateway.routes.byok.list_byok_keys", _fake_list)
    response = await client.get("/api/v1/byok/keys", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert response.json() == []


async def test_get_keys_con_filtro_scope_type(
    client: AsyncClient, monkeypatch
) -> None:
    captured: dict = {}

    async def _fake_list(tenant_id: UUID, *, scope_type=None, scope_id=None):
        captured["tenant_id"] = tenant_id
        captured["scope_type"] = scope_type
        captured["scope_id"] = scope_id
        return []

    monkeypatch.setattr("ai_gateway.routes.byok.list_byok_keys", _fake_list)
    materia_id = str(uuid4())
    response = await client.get(
        f"/api/v1/byok/keys?scope_type=materia&scope_id={materia_id}",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert captured["scope_type"] == "materia"
    assert str(captured["scope_id"]) == materia_id


# ── POST /keys/{id}/rotate ─────────────────────────────────────────────


async def test_rotate_key_no_existe_404(client: AsyncClient, monkeypatch) -> None:
    async def _fake_rotate(*args, **kwargs):
        return None

    monkeypatch.setattr("ai_gateway.routes.byok.rotate_byok_key", _fake_rotate)
    key_id = str(uuid4())
    response = await client.post(
        f"/api/v1/byok/keys/{key_id}/rotate",
        json={"plaintext_value": "sk-newvalue-key12345"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 404


async def test_rotate_key_master_missing_500(
    client: AsyncClient, monkeypatch
) -> None:
    async def _fake_rotate(*args, **kwargs):
        raise ValueError("BYOK_MASTER_KEY no configurada")

    monkeypatch.setattr("ai_gateway.routes.byok.rotate_byok_key", _fake_rotate)
    response = await client.post(
        f"/api/v1/byok/keys/{uuid4()}/rotate",
        json={"plaintext_value": "sk-something-12345678"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 500


async def test_rotate_key_value_error_400(client: AsyncClient, monkeypatch) -> None:
    async def _fake_rotate(*args, **kwargs):
        raise ValueError("plaintext invalido por X")

    monkeypatch.setattr("ai_gateway.routes.byok.rotate_byok_key", _fake_rotate)
    response = await client.post(
        f"/api/v1/byok/keys/{uuid4()}/rotate",
        json={"plaintext_value": "sk-newvalue-key12345"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 400


async def test_rotate_plaintext_corto_422(client: AsyncClient) -> None:
    """min_length=8 en el schema."""
    response = await client.post(
        f"/api/v1/byok/keys/{uuid4()}/rotate",
        json={"plaintext_value": "abc"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422


async def test_rotate_happy_path(client: AsyncClient, monkeypatch) -> None:
    new_id = str(uuid4())

    async def _fake_rotate(tenant_id, key_id, plaintext):
        return {
            "id": str(key_id),
            "tenant_id": str(tenant_id),
            "scope_type": "tenant",
            "scope_id": None,
            "provider": "anthropic",
            "fingerprint_last4": "WXYZ",
            "monthly_budget_usd": None,
            "created_at": "2026-05-07T00:00:00+00:00",
            "created_by": VALID_USER,
            "revoked_at": None,
            "last_used_at": None,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.rotate_byok_key", _fake_rotate)
    response = await client.post(
        f"/api/v1/byok/keys/{new_id}/rotate",
        json={"plaintext_value": "sk-newrotated-WXYZ"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["fingerprint_last4"] == "WXYZ"


# ── POST /keys/{id}/revoke ─────────────────────────────────────────────


async def test_revoke_key_no_existe_404(client: AsyncClient, monkeypatch) -> None:
    async def _fake_revoke(*args, **kwargs):
        return None

    monkeypatch.setattr("ai_gateway.routes.byok.revoke_byok_key", _fake_revoke)
    response = await client.post(
        f"/api/v1/byok/keys/{uuid4()}/revoke", headers=ADMIN_HEADERS
    )
    assert response.status_code == 404


async def test_revoke_key_happy_path(client: AsyncClient, monkeypatch) -> None:
    key_id = str(uuid4())

    async def _fake_revoke(tenant_id, kid):
        return {
            "id": str(kid),
            "tenant_id": str(tenant_id),
            "scope_type": "tenant",
            "scope_id": None,
            "provider": "anthropic",
            "fingerprint_last4": "ABCD",
            "monthly_budget_usd": None,
            "created_at": "2026-05-07T00:00:00+00:00",
            "created_by": VALID_USER,
            "revoked_at": "2026-05-07T01:00:00+00:00",
            "last_used_at": None,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.revoke_byok_key", _fake_revoke)
    response = await client.post(
        f"/api/v1/byok/keys/{key_id}/revoke", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["revoked_at"] is not None


# ── GET /keys/{id}/usage ───────────────────────────────────────────────


async def test_get_usage_default_yyyymm(
    client: AsyncClient, monkeypatch
) -> None:
    """Sin yyyymm, el service computa el mes actual."""
    captured: dict = {}

    async def _fake_usage(tenant_id, kid, *, yyyymm=None):
        captured["yyyymm"] = yyyymm
        return {
            "key_id": str(kid),
            "yyyymm": "202605",
            "tokens_input_total": 0,
            "tokens_output_total": 0,
            "cost_usd_total": 0.0,
            "request_count": 0,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.get_byok_key_usage", _fake_usage)
    response = await client.get(
        f"/api/v1/byok/keys/{uuid4()}/usage", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    assert captured["yyyymm"] is None  # el service decide el default


async def test_get_usage_con_yyyymm(client: AsyncClient, monkeypatch) -> None:
    captured: dict = {}

    async def _fake_usage(tenant_id, kid, *, yyyymm=None):
        captured["yyyymm"] = yyyymm
        return {
            "key_id": str(kid),
            "yyyymm": yyyymm or "202604",
            "tokens_input_total": 100,
            "tokens_output_total": 50,
            "cost_usd_total": 0.05,
            "request_count": 3,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.get_byok_key_usage", _fake_usage)
    response = await client.get(
        f"/api/v1/byok/keys/{uuid4()}/usage?yyyymm=202604", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    assert captured["yyyymm"] == "202604"
    body = response.json()
    assert body["tokens_input_total"] == 100
    assert body["request_count"] == 3
