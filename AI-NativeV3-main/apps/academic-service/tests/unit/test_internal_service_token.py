"""Header X-Internal-Service-Token en llamadas salientes directas (A0.1).

academic-service pega DIRECTO (sin api-gateway) al ai-gateway (generación IA)
y al classifier (config-hash). Cuando esos servicios exigen procedencia
(`require_gateway_signature`), aceptan el token compartido de plataforma via
`X-Internal-Service-Token`. Con el token vacío (default) el header NO se manda
(backward-compat: comportamiento idéntico al actual).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from academic_service.config import settings
from academic_service.services.ai_clients import AIGatewayClient


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"content": "ok", "model": "m", "provider": "p", "feature": "f"}


class _FakeAsyncClient:
    """Captura los headers del último POST para inspección en el test."""

    last_headers: dict[str, str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, *, json: Any, headers: dict[str, str]) -> _FakeResponse:
        type(self).last_headers = headers
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _reset_token() -> Any:
    original = settings.internal_service_token
    _FakeAsyncClient.last_headers = None
    yield
    settings.internal_service_token = original


async def _run_complete(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr("academic_service.services.ai_clients.httpx.AsyncClient", _FakeAsyncClient)
    client = AIGatewayClient(base_url="http://ai-gateway:8011")
    await client.complete(
        messages=[{"role": "user", "content": "x"}],
        model="m",
        feature="tp_generator",
        tenant_id=uuid4(),
    )
    assert _FakeAsyncClient.last_headers is not None
    return _FakeAsyncClient.last_headers


async def test_header_presente_con_token_seteado(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.internal_service_token = "shared-secret-123"
    headers = await _run_complete(monkeypatch)
    assert headers.get("X-Internal-Service-Token") == "shared-secret-123"


async def test_header_ausente_con_token_vacio(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.internal_service_token = ""
    headers = await _run_complete(monkeypatch)
    assert "X-Internal-Service-Token" not in headers
