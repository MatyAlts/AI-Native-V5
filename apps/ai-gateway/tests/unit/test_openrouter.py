"""Tests del ruteo OpenRouter (motor global) + seguridad KEYLESS.

Cubre el provider OpenRouter agregado en `providers/base.py` y el ruteo por
namespace de `routes/complete.py`:

- `_infer_provider_name("google/gemini-2.5-flash")` -> "openrouter" cuando el
  modelo es namespaced.
- `_strip_namespace` saca el namespace para el fallback nativo.
- `_make_provider("openrouter", key)` instancia `OpenRouterProvider` con el
  `base_url` de OpenRouter.
- `_resolve_provider_and_model`:
    * con key openrouter resoluble -> OpenRouterProvider + modelo namespaced.
    * SIN key openrouter (FALLBACK KEYLESS, test critico de seguridad) -> strip
      del namespace + provider nativo con el modelo sin namespace. Un deploy sin
      OPENROUTER_API_KEY NO debe romper: cae al provider nativo / mock.
- BYOK acepta `provider="openrouter"` en el CRUD de keys (Literal whitelist).

Mockea el SDK OpenAI con AsyncMock siguiendo el patron de `test_providers.py`
y `test_complete_routes.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ai_gateway.providers.base import (
    CompletionRequest,
    MockProvider,
    OpenRouterProvider,
    get_provider,
)
from ai_gateway.routes import complete as complete_module
from ai_gateway.routes.complete import (
    _infer_provider_name,
    _make_provider,
    _resolve_provider_and_model,
    _strip_namespace,
)
from ai_gateway.services.byok import ResolvedKey
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


# ── (a) _infer_provider_name: namespaced -> openrouter ──────────────────


def test_infer_provider_name_namespaced_routea_a_openrouter() -> None:
    """Cualquier modelo con `/` (namespaced) se clasifica como openrouter."""
    assert _infer_provider_name("google/gemini-2.5-flash") == "openrouter"
    assert _infer_provider_name("openai/gpt-4o-mini") == "openrouter"
    assert _infer_provider_name("anthropic/claude-3.5-sonnet") == "openrouter"


def test_infer_provider_name_sin_namespace_usa_provider_nativo() -> None:
    """Sin `/`, se infiere el provider nativo por prefijo del nombre."""
    assert _infer_provider_name("gpt-4o-mini") == "openai"
    assert _infer_provider_name("gemini-2.5-flash") == "gemini"
    assert _infer_provider_name("claude-sonnet-4-6") == "anthropic"
    assert _infer_provider_name("mistral-large-latest") == "mistral"


def test_strip_namespace() -> None:
    assert _strip_namespace("google/gemini-2.5-flash") == "gemini-2.5-flash"
    assert _strip_namespace("openai/gpt-4o-mini") == "gpt-4o-mini"
    # Sin namespace -> no-op.
    assert _strip_namespace("gpt-4o-mini") == "gpt-4o-mini"
    # Solo el PRIMER `/` separa el namespace.
    assert _strip_namespace("openrouter/openai/gpt-4o") == "openai/gpt-4o"


# ── (c) _make_provider("openrouter", key) -> OpenRouterProvider ─────────


def test_make_provider_openrouter_instancia_clase_correcta() -> None:
    provider = _make_provider("openrouter", "sk-or-fake-key")
    assert isinstance(provider, OpenRouterProvider)
    assert provider.name == "openrouter"
    assert provider.api_key == "sk-or-fake-key"


def test_openrouter_ensure_client_usa_base_url_de_openrouter(monkeypatch) -> None:
    """El cliente AsyncOpenAI del OpenRouterProvider apunta al base_url de
    OpenRouter + headers de atribucion. Mockeamos el SDK para capturar kwargs."""
    # Sin override de env -> usa el default canonico de OpenRouter.
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)

    captured: dict = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_module = MagicMock()
    fake_module.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(__import__("sys").modules, "openai", fake_module)

    provider = OpenRouterProvider(api_key="sk-or-fake")
    client = provider._ensure_client()

    # El cliente cacheado es la instancia del SDK (mockeado) que capturo kwargs.
    assert isinstance(client, FakeAsyncOpenAI)
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "sk-or-fake"
    # Headers de atribucion recomendados por OpenRouter.
    assert "HTTP-Referer" in captured["default_headers"]
    assert "X-Title" in captured["default_headers"]


async def test_openrouter_complete_lee_costo_real_del_usage() -> None:
    """OpenRouter devuelve `usage.cost` (USD) con `usage:{include:true}`; el
    provider NO mantiene tabla PRICING propia, confia en ese costo real."""
    choice = MagicMock()
    choice.message = MagicMock(content="respuesta openrouter")
    usage = MagicMock(prompt_tokens=120, completion_tokens=60, cost=0.0042)
    result = MagicMock()
    result.choices = [choice]
    result.usage = usage

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=result)

    provider = OpenRouterProvider(api_key="sk-or-fake")
    provider._client = client

    req = CompletionRequest(
        messages=[{"role": "user", "content": "hola"}],
        model="openai/gpt-4o-mini",
        temperature=0.0,
        max_tokens=256,
    )
    response = await provider.complete(req)
    assert response.content == "respuesta openrouter"
    assert response.provider == "openrouter"
    assert response.input_tokens == 120
    assert response.output_tokens == 60
    assert response.cost_usd == pytest.approx(0.0042)
    # Pide el costo real via extra_body usage include.
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["extra_body"] == {"usage": {"include": True}}
    assert call_kwargs["model"] == "openai/gpt-4o-mini"


# ── _resolve_provider_and_model: con key openrouter -> openrouter ───────


async def test_resolve_con_key_openrouter_usa_openrouter_y_modelo_namespaced(
    monkeypatch,
) -> None:
    """Modelo namespaced + key openrouter resoluble -> OpenRouterProvider con el
    modelo namespaced TAL CUAL (sin strip)."""

    async def _fake_resolve(*, tenant_id, provider, materia_id):
        if provider == "openrouter":
            return ResolvedKey(
                plaintext="sk-or-real",
                provider="openrouter",
                scope_resolved="tenant",
                key_id=uuid4(),
                monthly_budget_usd=None,
            )
        return None

    monkeypatch.setattr(complete_module, "resolve_byok_key", _fake_resolve)

    provider, effective_model, resolved = await _resolve_provider_and_model(
        tenant_id=uuid4(), model="google/gemini-2.5-flash", materia_id=None
    )
    assert isinstance(provider, OpenRouterProvider)
    assert effective_model == "google/gemini-2.5-flash"  # sin strip
    assert resolved is not None
    assert resolved.provider == "openrouter"


# ── (b) FALLBACK KEYLESS — test CRITICO de seguridad ────────────────────


async def test_resolve_keyless_fallback_strippea_namespace_y_cae_a_nativo(
    monkeypatch,
) -> None:
    """SIN key openrouter ni key nativa, un modelo namespaced se STRIPPEA y cae al
    provider nativo (get_provider -> mock en dev). Un deploy sin OPENROUTER_API_KEY
    NO debe romper: se comporta como ruteo nativo directo con el modelo sin
    namespace. ESTE es el invariante de seguridad keyless."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_provider.cache_clear()

    async def _no_key(*, tenant_id, provider, materia_id):
        return None  # NINGUNA key resoluble (ni openrouter ni nativa)

    monkeypatch.setattr(complete_module, "resolve_byok_key", _no_key)

    provider, effective_model, resolved = await _resolve_provider_and_model(
        tenant_id=uuid4(), model="openai/gpt-4o-mini", materia_id=None
    )
    # No rompe: cae al provider de dev (mock) con el modelo SIN namespace.
    assert isinstance(provider, MockProvider)
    assert effective_model == "gpt-4o-mini"  # namespace strippeado
    assert resolved is None


async def test_resolve_keyless_fallback_usa_key_nativa_si_existe(
    monkeypatch,
) -> None:
    """SIN key openrouter pero CON key nativa del provider strippeado: se usa el
    provider nativo (gemini) con el modelo sin namespace y la key nativa."""

    async def _only_native(*, tenant_id, provider, materia_id):
        if provider == "openrouter":
            return None  # no hay key openrouter
        if provider == "gemini":
            return ResolvedKey(
                plaintext="gemini-native-key",
                provider="gemini",
                scope_resolved="tenant",
                key_id=uuid4(),
                monthly_budget_usd=None,
            )
        return None

    monkeypatch.setattr(complete_module, "resolve_byok_key", _only_native)

    # Stub _make_provider para no instanciar el SDK real de gemini.
    captured: dict = {}

    def _fake_make(name, key):
        captured["name"] = name
        captured["key"] = key
        return MockProvider()

    monkeypatch.setattr(complete_module, "_make_provider", _fake_make)

    _provider, effective_model, resolved = await _resolve_provider_and_model(
        tenant_id=uuid4(), model="google/gemini-2.5-flash", materia_id=None
    )
    assert effective_model == "gemini-2.5-flash"  # strippeado
    assert resolved is not None
    assert resolved.provider == "gemini"
    assert captured["name"] == "gemini"
    assert captured["key"] == "gemini-native-key"


# ── (d) BYOK acepta provider="openrouter" ───────────────────────────────


@pytest.fixture
async def byok_client() -> AsyncClient:
    from ai_gateway.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


_ADMIN_HEADERS = {
    "X-Tenant-Id": "11111111-1111-1111-1111-111111111111",
    "X-User-Id": "22222222-2222-2222-2222-222222222222",
    "X-User-Roles": "superadmin",
}


async def test_byok_create_acepta_provider_openrouter(
    byok_client: AsyncClient, monkeypatch
) -> None:
    """El CRUD de BYOK acepta `provider="openrouter"` (Literal whitelist). El
    create se mockea — solo verificamos que el schema NO rechaza openrouter."""
    fake_id = str(uuid4())

    async def _fake_create(**kwargs):
        assert kwargs["provider"] == "openrouter"
        return {
            "id": fake_id,
            "tenant_id": _ADMIN_HEADERS["X-Tenant-Id"],
            "scope_type": "tenant",
            "scope_id": None,
            "provider": "openrouter",
            "fingerprint_last4": "or12",
            "monthly_budget_usd": None,
            "created_at": "2026-06-30T00:00:00+00:00",
            "created_by": _ADMIN_HEADERS["X-User-Id"],
            "revoked_at": None,
            "last_used_at": None,
        }

    monkeypatch.setattr("ai_gateway.routes.byok.create_byok_key", _fake_create)

    body = {
        "scope_type": "tenant",
        "scope_id": None,
        "provider": "openrouter",
        "plaintext_value": "sk-or-v1-validlength-key",
    }
    response = await byok_client.post("/api/v1/byok/keys", json=body, headers=_ADMIN_HEADERS)
    assert response.status_code in (200, 201)
    assert response.json()["provider"] == "openrouter"


async def test_byok_create_whitelist_acepta_openrouter(monkeypatch) -> None:
    """`create_byok_key` valida el provider contra la whitelist; openrouter NO
    debe disparar el `ValueError('provider invalido')`. Forzamos master key
    ausente para cortar ANTES del DB y aislar la validacion de provider."""
    from ai_gateway.services import byok as byok_service

    # Master key None -> el error es de master key, NO de provider invalido,
    # confirmando que "openrouter" paso la whitelist de providers.
    monkeypatch.setattr(byok_service, "_get_master_key_bytes", lambda: None)

    with pytest.raises(ValueError) as exc:
        await byok_service.create_byok_key(
            tenant_id=uuid4(),
            user_id=uuid4(),
            scope_type="tenant",
            scope_id=None,
            provider="openrouter",
            plaintext_value="sk-or-v1-validlength",
            monthly_budget_usd=None,
        )
    assert "provider invalido" not in str(exc.value)
    assert "BYOK_MASTER_KEY" in str(exc.value)
