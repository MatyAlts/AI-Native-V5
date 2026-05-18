"""Smoke #6 — governance + ai-gateway con LLM mock.

Atrapa:
  - governance-service no carga prompts del filesystem (PROMPTS_REPO_PATH mal seteado)
  - manifest.yaml ↔ default_prompt_version desincronizados
  - ai-gateway con mock LLM caído
  - x-caller header validation rota

Notas de routing:
  - `/api/v1/active_configs` NO está en el ROUTE_MAP del api-gateway (no es
    un endpoint público). Pegamos directo a :8010.
  - `/api/v1/complete` tampoco está expuesto al frontend (LLM proxy interno).
    Pegamos directo a :8011.
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.smoke
def test_active_configs_returns_versions() -> None:
    """GET :8010/api/v1/active_configs → mapping de prompt → version activa.

    G12: el manifest declara qué versión de cada prompt es la 'activa' para
    frontends/dashboards. Si el archivo no se parsea, este endpoint da 500.
    """
    resp = httpx.get("http://127.0.0.1:8010/api/v1/active_configs", timeout=3.0)
    assert resp.status_code == 200, (
        f"governance /active_configs falló: {resp.status_code} {resp.text[:300]}"
    )
    body = resp.json()
    assert "active" in body, f"esperaba campo 'active' en response: {body}"
    # Estructura esperada: active.{tenant|default}.{prompt_name: version}
    active = body["active"]
    assert isinstance(active, dict) and active, "active dict no debe estar vacío"
    # Al menos un prompt 'tutor' configurado
    flat_versions = {}
    for tenant_block in active.values():
        if isinstance(tenant_block, dict):
            flat_versions.update(tenant_block)
    assert "tutor" in flat_versions, (
        f"esperaba prompt 'tutor' configurado en algún tenant. got keys: {flat_versions.keys()}"
    )


@pytest.mark.smoke
def test_governance_returns_tutor_prompt_v1_0_0() -> None:
    """GET :8010/api/v1/prompts/tutor/v1.0.0 → contenido del system prompt.

    El tutor-service hace este llamado al abrir cada episodio. Si el prompt
    no se carga, todo el flujo pedagógico cascada.
    """
    resp = httpx.get("http://127.0.0.1:8010/api/v1/prompts/tutor/v1.0.0", timeout=3.0)
    assert resp.status_code == 200, (
        f"governance prompts/tutor/v1.0.0 falló: {resp.status_code} {resp.text[:300]}"
    )
    body = resp.json()
    # Esperado: campos {content, hash, version} o similares
    assert any(k in body for k in ("content", "system_md", "body", "hash")), (
        f"esperaba content/hash en prompt response: {body.keys()}"
    )


@pytest.mark.smoke
def test_ai_gateway_complete_with_mock_provider() -> None:
    """POST :8011/api/v1/complete → mock provider responde determinísticamente.

    Los defaults de dev tienen LLM_PROVIDER=mock. Sin eso el test consume
    budget real.
    """
    payload = {
        "messages": [{"role": "user", "content": "hola"}],
        "model": "mock-1",
        "feature": "smoke_test",
    }
    headers = {
        "X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "X-Caller": "smoke-test",
    }
    resp = httpx.post(
        "http://127.0.0.1:8011/api/v1/complete",
        json=payload,
        headers=headers,
        timeout=5.0,
    )
    assert resp.status_code == 200, (
        f"ai-gateway /complete falló: {resp.status_code} {resp.text[:300]}"
    )
    body = resp.json()
    assert body["provider"] == "mock", (
        f"esperaba provider=mock — si es otro, el dev mock se rompió. got={body['provider']}"
    )
    assert "[mock respuesta para:" in body["content"]
    assert body["cost_usd"] == 0.0


@pytest.mark.smoke
def test_ai_gateway_complete_requires_x_caller() -> None:
    """Sin X-Caller → 422 (FastAPI dependency missing)."""
    payload = {
        "messages": [{"role": "user", "content": "hola"}],
        "model": "mock-1",
        "feature": "smoke",
    }
    headers = {"X-Tenant-Id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
    resp = httpx.post(
        "http://127.0.0.1:8011/api/v1/complete",
        json=payload,
        headers=headers,
        timeout=3.0,
    )
    assert resp.status_code == 422, (
        f"esperaba 422 sin x-caller. got={resp.status_code} body={resp.text[:200]}"
    )
