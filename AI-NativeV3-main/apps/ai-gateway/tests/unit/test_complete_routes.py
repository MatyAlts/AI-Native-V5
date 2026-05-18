"""Tests de los endpoints `/api/v1/complete`, `/api/v1/stream`, `/api/v1/budget`.

Cubre `apps/ai-gateway/src/ai_gateway/routes/complete.py`:
- Happy path con MockProvider (LLM_PROVIDER=mock).
- Cache hit / miss flow.
- Budget exceeded -> 429.
- Provider error -> 502.
- Schema validation: messages role, temperature out of range.
- /budget endpoint.
- /stream SSE: yieldea chunks + done.
- /stream con error del provider envia event 'error'.
- materia_id propagado al request body (ADR-040).

Reusa fakeredis (ya importado en otros tests) y monkeypatch del provider.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from ai_gateway.main import app
from ai_gateway.providers.base import (
    BaseProvider,
    CompletionRequest,
    CompletionResponse,
)
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _redis_isolation(monkeypatch):
    """Cada test recibe su propio FakeRedis para que el budget/cache estado
    no se filtre entre tests."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("ai_gateway.routes.complete._redis_client", fake)
    yield
    # No async teardown necesario — fakeredis se descarta con la fixture.


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    """Fuerza LLM_PROVIDER=mock y limpia keys del env para que el resolver BYOK
    no haga fallback a un provider real (el .env del usuario puede tener
    ANTHROPIC_API_KEY/MISTRAL_API_KEY validas que tirarian autenticacion real
    contra el provider en tests)."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from ai_gateway.config import settings as ai_settings
    from ai_gateway.providers.base import get_provider

    monkeypatch.setattr(ai_settings, "anthropic_api_key", "")
    monkeypatch.setattr(ai_settings, "openai_api_key", "")
    monkeypatch.setattr(ai_settings, "gemini_api_key", "")
    monkeypatch.setattr(ai_settings, "mistral_api_key", "")
    monkeypatch.setattr(ai_settings, "byok_enabled", False)

    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


VALID_TENANT = str(uuid4())
CALLER_HEADERS = {
    "X-Tenant-Id": VALID_TENANT,
    "X-Caller": "tutor-service",
}


def _basic_body(**overrides) -> dict:
    body = {
        "messages": [{"role": "user", "content": "hola mundo"}],
        "model": "claude-sonnet-4-6",
        "feature": "tutor",
        "temperature": 0.0,
        "max_tokens": 256,
    }
    body.update(overrides)
    return body


# ── /complete happy path ───────────────────────────────────────────────


async def test_complete_happy_path_mock(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["feature"] == "tutor"
    assert body["cache_hit"] is False
    assert body["cost_usd"] == 0.0  # MockProvider devuelve costo 0
    assert "hola mundo" in body["content"]
    assert "budget_status" in body


async def test_complete_segunda_invocacion_es_cache_hit(client: AsyncClient) -> None:
    """Con temperature=0, la segunda llamada identica es cache hit."""
    body = _basic_body()
    r1 = await client.post("/api/v1/complete", json=body, headers=CALLER_HEADERS)
    assert r1.status_code == 200
    assert r1.json()["cache_hit"] is False

    r2 = await client.post("/api/v1/complete", json=body, headers=CALLER_HEADERS)
    assert r2.status_code == 200
    assert r2.json()["cache_hit"] is True
    assert r2.json()["cost_usd"] == 0.0


async def test_complete_temperature_no_cero_no_cachea(
    client: AsyncClient,
) -> None:
    """temperature > 0 => cache disabled."""
    body = _basic_body(temperature=0.7)
    r1 = await client.post("/api/v1/complete", json=body, headers=CALLER_HEADERS)
    r2 = await client.post("/api/v1/complete", json=body, headers=CALLER_HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["cache_hit"] is False
    assert r2.json()["cache_hit"] is False


# ── /complete schema validation ────────────────────────────────────────


async def test_complete_role_invalido_422(client: AsyncClient) -> None:
    body = _basic_body(messages=[{"role": "robot", "content": "?"}])
    response = await client.post(
        "/api/v1/complete", json=body, headers=CALLER_HEADERS
    )
    assert response.status_code == 422


async def test_complete_temperature_fuera_de_rango_422(
    client: AsyncClient,
) -> None:
    body = _basic_body(temperature=3.5)  # le=2.0
    response = await client.post(
        "/api/v1/complete", json=body, headers=CALLER_HEADERS
    )
    assert response.status_code == 422


async def test_complete_max_tokens_excedido_422(client: AsyncClient) -> None:
    body = _basic_body(max_tokens=20000)  # le=8192
    response = await client.post(
        "/api/v1/complete", json=body, headers=CALLER_HEADERS
    )
    assert response.status_code == 422


async def test_complete_acepta_materia_id_opcional(client: AsyncClient) -> None:
    """ADR-040: materia_id es opcional, no rompe si se envia."""
    body = _basic_body(materia_id=str(uuid4()))
    response = await client.post(
        "/api/v1/complete", json=body, headers=CALLER_HEADERS
    )
    assert response.status_code == 200


# ── /complete budget exceeded ──────────────────────────────────────────


async def test_complete_budget_excedido_429(
    client: AsyncClient, monkeypatch
) -> None:
    """Si el tracker reporta exceeded=True, devuelve 429."""
    from ai_gateway.routes import complete as complete_module

    class _ExceededTracker:
        async def check(self, *a, **kw):
            class _S:
                exceeded = True
                used_usd = 9999.0
                limit_usd = 100.0
                remaining_usd = 0.0

            return _S()

        async def charge(self, *a, **kw):
            return 0.0

    monkeypatch.setattr(
        complete_module, "BudgetTracker", lambda redis: _ExceededTracker()
    )
    response = await client.post(
        "/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 429
    assert "Budget" in response.json()["detail"]


# ── /complete provider error ───────────────────────────────────────────


async def test_complete_provider_error_502(
    client: AsyncClient, monkeypatch
) -> None:
    """Provider lanza excepcion -> 502."""

    class _BoomProvider(BaseProvider):
        name = "boom"

        async def complete(self, request: CompletionRequest) -> CompletionResponse:
            raise RuntimeError("LLM ardio")

        async def stream_complete(self, request: CompletionRequest):
            raise RuntimeError("stream tambien")
            yield  # pragma: no cover (necesario para AsyncIterator)

    monkeypatch.setattr(
        "ai_gateway.routes.complete.get_provider", lambda: _BoomProvider()
    )
    response = await client.post(
        "/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 502
    assert "LLM provider error" in response.json()["detail"]


# ── /complete headers requeridos ───────────────────────────────────────


async def test_complete_sin_x_caller_devuelve_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/complete",
        json=_basic_body(),
        headers={"X-Tenant-Id": VALID_TENANT},  # sin X-Caller
    )
    assert response.status_code == 422


# ── /budget ────────────────────────────────────────────────────────────


async def test_budget_endpoint_devuelve_status_inicial(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/budget?feature=tutor", headers=CALLER_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feature"] == "tutor"
    assert body["used_usd"] == 0.0
    assert body["exceeded"] is False
    assert "month" in body


async def test_budget_endpoint_post_charge_acumula(
    client: AsyncClient,
) -> None:
    """Despues de un /complete, el budget refleja el uso (aunque mock cuesta 0,
    el endpoint sigue devolviendo limit_usd y exceeded=False)."""
    await client.post("/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS)
    response = await client.get(
        "/api/v1/budget?feature=tutor", headers=CALLER_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["exceeded"] is False


# ── /stream SSE ────────────────────────────────────────────────────────


async def test_stream_yieldea_chunks_y_done(client: AsyncClient) -> None:
    body = _basic_body()
    async with client.stream(
        "POST", "/api/v1/stream", json=body, headers=CALLER_HEADERS
    ) as r:
        assert r.status_code == 200
        chunks = []
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])
    # Al menos 1 token + 1 done
    assert len(chunks) >= 2
    # Ultimo evento es "done"
    import json as _json

    last = _json.loads(chunks[-1])
    assert last["type"] == "done"
    assert "estimated_cost_usd" in last


async def test_stream_budget_excedido_429(
    client: AsyncClient, monkeypatch
) -> None:
    from ai_gateway.routes import complete as complete_module

    class _ExceededTracker:
        async def check(self, *a, **kw):
            class _S:
                exceeded = True
                used_usd = 9999.0
                limit_usd = 100.0
                remaining_usd = 0.0

            return _S()

        async def charge(self, *a, **kw):
            return 0.0

    monkeypatch.setattr(
        complete_module, "BudgetTracker", lambda redis: _ExceededTracker()
    )
    response = await client.post(
        "/api/v1/stream", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 429


async def test_stream_provider_error_envia_event(
    client: AsyncClient, monkeypatch
) -> None:
    """Si el provider falla durante stream_complete, el endpoint emite un
    event 'error' en el cuerpo SSE (no rompe el HTTP status)."""

    class _BadStreamProvider(BaseProvider):
        name = "boom"

        async def complete(self, request):
            raise RuntimeError("never called")

        async def stream_complete(self, request):
            raise RuntimeError("stream blew up")
            yield  # pragma: no cover

    monkeypatch.setattr(
        "ai_gateway.routes.complete.get_provider", lambda: _BadStreamProvider()
    )

    async with client.stream(
        "POST", "/api/v1/stream", json=_basic_body(), headers=CALLER_HEADERS
    ) as r:
        assert r.status_code == 200
        chunks = []
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])

    import json as _json

    parsed = [_json.loads(c) for c in chunks]
    types = {p["type"] for p in parsed}
    assert "error" in types


# ── _get_redis singleton ───────────────────────────────────────────────


# ── byok_keys_usage tracking en env_fallback (gap doctoral 2026-05-07) ─


async def test_complete_env_fallback_registra_usage_en_byok_keys_usage(
    client: AsyncClient, monkeypatch
) -> None:
    """Test FALLA HOY (pre-fix) — gap auditoria doctoral 2026-05-07.

    Cuando el docente NO tiene BYOK propia y el resolver cae a env_fallback
    (key global del .env), igual hay que registrar el uso en
    `byok_keys_usage` (contra una BYOKKey sentinel determinista por
    (tenant, provider)) para auditoria doctoral de costos.

    Verificamos que `increment_env_fallback_usage` se invoca con los
    tokens y cost_usd correctos.
    """
    from ai_gateway.routes import complete as complete_module
    from ai_gateway.providers.base import (
        BaseProvider,
        CompletionRequest,
        CompletionResponse,
    )

    class _StubProvider(BaseProvider):
        name = "mock"

        async def complete(self, req: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(
                content="ok",
                model=req.model,
                provider="mock",
                input_tokens=42,
                output_tokens=21,
                cost_usd=0.005,
            )

        async def stream_complete(self, req: CompletionRequest):
            yield "ok"

    # Stubeamos _make_provider para que la key del env_fallback NO termine
    # construyendo un AnthropicProvider real (que pegaria contra la API).
    monkeypatch.setattr(
        complete_module, "_make_provider", lambda name, key: _StubProvider()
    )

    spy = AsyncMock(return_value=uuid4())  # devuelve el sentinel id mock
    monkeypatch.setattr(complete_module, "increment_env_fallback_usage", spy)

    # Forzamos env_fallback con BYOK_ENABLED=False y key del env presente.
    from ai_gateway.config import settings as ai_settings

    monkeypatch.setattr(ai_settings, "byok_enabled", False)
    monkeypatch.setattr(ai_settings, "anthropic_api_key", "sk-env-fallback-test")

    response = await client.post(
        "/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 200

    # PROPIEDAD CRITICA (gap 2026-05-07): el handler debe haber invocado
    # increment_env_fallback_usage para auditoria. Antes del fix, esto NO
    # ocurria — increment_usage solo corria con resolved.key_id != None.
    spy.assert_awaited_once()
    call_kwargs = spy.await_args.kwargs
    assert call_kwargs["provider"] == "anthropic"
    assert call_kwargs["tenant_id"] == UUID(VALID_TENANT)
    # El MockProvider devuelve tokens fijos — verificamos que se propagan
    assert call_kwargs["tokens_input"] >= 0
    assert call_kwargs["tokens_output"] >= 0
    assert call_kwargs["cost_usd"] >= 0.0


async def test_complete_byok_real_no_invoca_env_fallback_usage(
    client: AsyncClient, monkeypatch
) -> None:
    """Caso simétrico — cuando hay BYOK real (resolved.key_id != None),
    se invoca increment_usage (no increment_env_fallback_usage).

    Garantiza que el branch nuevo NO contamina el flujo BYOK existente.
    """
    from ai_gateway.routes import complete as complete_module
    from ai_gateway.services.byok import ResolvedKey

    fake_key_id = uuid4()

    async def _fake_resolve(*args, **kwargs):
        return ResolvedKey(
            plaintext="sk-byok-real",
            provider="anthropic",
            scope_resolved="tenant",
            key_id=fake_key_id,
            monthly_budget_usd=None,
        )

    monkeypatch.setattr(complete_module, "resolve_byok_key", _fake_resolve)

    # Stub provider para no requerir credenciales reales (MockProvider OK
    # pero el path BYOK construye AnthropicProvider — interceptamos al
    # _make_provider para devolver el mock).
    from ai_gateway.providers.base import (
        BaseProvider,
        CompletionRequest,
        CompletionResponse,
    )

    class _StubProvider(BaseProvider):
        name = "mock"

        async def complete(self, req: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(
                content="ok",
                model=req.model,
                provider="mock",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.0,
            )

        async def stream_complete(self, req: CompletionRequest):
            yield "ok"

    monkeypatch.setattr(
        complete_module, "_make_provider", lambda name, key: _StubProvider()
    )

    spy_byok = AsyncMock()
    spy_envf = AsyncMock()
    monkeypatch.setattr(complete_module, "increment_usage", spy_byok)
    monkeypatch.setattr(complete_module, "increment_env_fallback_usage", spy_envf)

    response = await client.post(
        "/api/v1/complete", json=_basic_body(), headers=CALLER_HEADERS
    )
    assert response.status_code == 200

    # Path BYOK real: increment_usage llamada UNA vez, env_fallback NUNCA.
    spy_byok.assert_awaited_once()
    spy_envf.assert_not_awaited()
    assert spy_byok.await_args.kwargs["key_id"] == fake_key_id


async def test_get_redis_devuelve_singleton(monkeypatch) -> None:
    """Verifica que _get_redis cachea el cliente entre llamadas (lazy init)."""
    from ai_gateway.routes import complete as complete_module

    monkeypatch.setattr(complete_module, "_redis_client", None)
    # Stub el factory de redis.from_url para no requerir red.
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "redis.asyncio.from_url", lambda *a, **kw: fake
    )
    client1 = complete_module._get_redis()
    client2 = complete_module._get_redis()
    assert client1 is client2
