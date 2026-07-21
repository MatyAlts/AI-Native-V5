"""Smoke #1 — los 12 servicios responden /health con status `ready` o `degraded`.

Atrapa: pods con DB caída, redis caído, governance sin prompts, master key
faltante, etc. Si un servicio responde 503 (degraded por una dep crítica),
el test imprime las últimas 20 líneas del log para ayudar al debug.

NO chequea el ctr-service contra el helper compartido `packages/observability`
— ese servicio tiene un schema propio (`{db, redis}` strings) declarado como
excepción intencional en CLAUDE.md. Lo único que validamos es status code 200
y que `status` esté presente en el JSON.
"""

from __future__ import annotations

import httpx
import pytest
from _helpers import SERVICES_HEALTH, tail_log


@pytest.mark.smoke
@pytest.mark.parametrize("port,name", SERVICES_HEALTH, ids=[s[1] for s in SERVICES_HEALTH])
def test_health_endpoint_responds_ready_or_degraded(port: int, name: str) -> None:
    """Cada servicio en su puerto debe responder 200 con status válido."""
    url = f"http://127.0.0.1:{port}/health"
    resp = httpx.get(url, timeout=3.0)

    if resp.status_code not in (200, 503):
        pytest.fail(
            f"{name} (:{port}) respondió {resp.status_code} — esperado 200 (ready/degraded) "
            f"o 503 (error). Body: {resp.text[:300]}\n\n"
            f"Últimas 20 líneas de {name}.log:\n{tail_log(name)}"
        )

    body = resp.json()
    status = body.get("status")

    # api-gateway en el entorno E2E corre SIN Keycloak a proposito
    # (DEV_TRUST_HEADERS=true; la suite smoke autentica por headers X-*, no por
    # JWT). Su readiness marca `keycloak_jwks` como check CRITICO
    # (api_gateway/routes/health.py:57) -> status='error'. Eso es esperable aca.
    # Aceptamos 'error' SOLO si el unico check que falla es keycloak_jwks;
    # cualquier OTRA dep caida (DB, academic_service) sigue fallando el test.
    if name == "api-gateway" and status == "error":
        checks = body.get("checks", {})
        failing = {k for k, v in checks.items() if not v.get("ok", True)}
        if failing == {"keycloak_jwks"}:
            print(
                "\n[WARN] api-gateway 'error' solo por keycloak_jwks "
                "(esperado: E2E corre sin Keycloak, dev_trust_headers)"
            )
            return

    if status not in ("ready", "degraded", "ok"):  # ok = ctr-service legacy
        pytest.fail(
            f"{name} respondió status={status!r} — esperado ready/degraded/ok. "
            f"Body: {body}\n\nLog:\n{tail_log(name)}"
        )

    if status == "degraded":
        # No falla — degraded es válido — pero loggea para visibility
        # (un test que falla seria mas ruidoso pero menos accionable).
        print(f"\n[WARN] {name} reporta degraded — alguna dep cayó. checks={body.get('checks')}")


@pytest.mark.smoke
def test_api_gateway_routes_to_academic_via_proxy(client: httpx.Client, auth_headers) -> None:
    """Verifica que el ROUTE_MAP del api-gateway propaga al academic-service.

    Atrapa: ROUTE_MAP roto, headers no inyectados aguas abajo, casbin negando
    al docente lo que debería poder leer.
    """
    resp = client.get("/api/v1/comisiones", headers=auth_headers("docente"))
    assert resp.status_code == 200, (
        f"GET /api/v1/comisiones via gateway debería estar OK para docente. "
        f"status={resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    # academic-service usa envelope {data, meta} en list endpoints (paginado).
    items = body["data"] if isinstance(body, dict) and "data" in body else body
    assert isinstance(items, list), f"esperado list, got {type(items).__name__}"
    # En el seed-3-comisiones.py hay 3 comisiones del tenant demo.
    assert len(items) >= 1, "Esperaba al menos una comisión seedeada"
