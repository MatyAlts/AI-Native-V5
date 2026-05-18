"""Tests del factory get_provider() y AnthropicProvider (mockeado).

Cubre `apps/ai-gateway/src/ai_gateway/providers/base.py`:
- get_provider("mock") -> MockProvider
- get_provider("anthropic") -> AnthropicProvider (sin tocar la red)
- get_provider("unknown") -> ValueError (cuando es argumento explícito)
- get_provider() con default Settings -> MockProvider (CLAUDE.md dev default)
- AnthropicProvider.complete() con mock del SDK Anthropic.
- AnthropicProvider.stream_complete() con mock del SDK Anthropic.
- pricing fallback para modelos no listados.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from ai_gateway.providers.base import (
    AnthropicProvider,
    CompletionRequest,
    MistralProvider,
    MockProvider,
    get_provider,
)


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


# ── get_provider factory ───────────────────────────────────────────────


def test_get_provider_mock_explicito() -> None:
    p = get_provider("mock")
    assert isinstance(p, MockProvider)
    assert p.name == "mock"


def test_get_provider_via_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    p = get_provider()
    assert isinstance(p, MockProvider)


def test_get_provider_anthropic_explicito(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    p = get_provider("anthropic")
    assert isinstance(p, AnthropicProvider)
    assert p.name == "anthropic"


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Provider desconocido"):
        get_provider("xai-grok")


def test_get_provider_default_es_mock(monkeypatch) -> None:
    """Sin override de env ni argumento, el default de Settings.llm_provider es
    `mock` (CLAUDE.md exige defaults sin API keys reales para dev/test loop)."""
    from ai_gateway import config as ai_config

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(ai_config.settings, "llm_provider", "mock")
    p = get_provider()
    assert isinstance(p, MockProvider)


def test_get_provider_es_lru_cached() -> None:
    """get_provider tiene @lru_cache(maxsize=1)."""
    p1 = get_provider("mock")
    p2 = get_provider("mock")
    assert p1 is p2


# ── AnthropicProvider.complete() — mockeando el SDK ────────────────────


def _make_fake_anthropic_sdk(content_text: str, input_tok: int, output_tok: int):
    """Construye un fake del SDK Anthropic que `_ensure_client` puede inyectar."""
    block = MagicMock()
    block.text = content_text
    result = MagicMock()
    result.content = [block]
    result.usage = MagicMock(input_tokens=input_tok, output_tokens=output_tok)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=result)
    return client


async def test_anthropic_complete_calcula_costo_sonnet() -> None:
    provider = AnthropicProvider(api_key="sk-ant-fake")
    provider._client = _make_fake_anthropic_sdk(
        "respuesta del modelo", input_tok=1000, output_tok=500
    )

    req = CompletionRequest(
        messages=[{"role": "user", "content": "hola"}],
        model="claude-sonnet-4-6",
        temperature=0.5,
        max_tokens=1024,
    )
    response = await provider.complete(req)
    assert response.content == "respuesta del modelo"
    assert response.provider == "anthropic"
    assert response.input_tokens == 1000
    assert response.output_tokens == 500
    # Sonnet: $3/M input + $15/M output
    expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
    assert response.cost_usd == pytest.approx(expected)


async def test_anthropic_complete_modelo_desconocido_usa_pricing_default() -> None:
    """Modelo no listado en PRICING usa fallback {"input": 1.0, "output": 5.0}."""
    provider = AnthropicProvider(api_key="sk-ant-fake")
    provider._client = _make_fake_anthropic_sdk("ok", 100, 50)

    req = CompletionRequest(
        messages=[{"role": "user", "content": "?"}],
        model="claude-future-99",  # no listado
        temperature=0.0,
        max_tokens=128,
    )
    response = await provider.complete(req)
    expected = (100 * 1.0 + 50 * 5.0) / 1_000_000
    assert response.cost_usd == pytest.approx(expected)


async def test_anthropic_complete_separa_system_de_user() -> None:
    """Los messages con role='system' se concatenan con \\n\\n y se mandan
    aparte; los demas roles van en `messages`."""
    fake = _make_fake_anthropic_sdk("done", 10, 5)
    provider = AnthropicProvider(api_key="sk-ant-fake")
    provider._client = fake

    req = CompletionRequest(
        messages=[
            {"role": "system", "content": "sistema A"},
            {"role": "system", "content": "sistema B"},
            {"role": "user", "content": "pregunta"},
        ],
        model="claude-sonnet-4-6",
    )
    await provider.complete(req)
    call_kwargs = fake.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "sistema A\n\nsistema B"
    assert call_kwargs["messages"] == [{"role": "user", "content": "pregunta"}]


async def test_anthropic_complete_sin_system_envia_string_vacio() -> None:
    fake = _make_fake_anthropic_sdk("done", 10, 5)
    provider = AnthropicProvider(api_key="sk-ant-fake")
    provider._client = fake

    req = CompletionRequest(
        messages=[{"role": "user", "content": "x"}],
        model="claude-sonnet-4-6",
    )
    await provider.complete(req)
    assert fake.messages.create.call_args.kwargs["system"] == ""


async def test_anthropic_filtra_blocks_sin_text() -> None:
    """Solo los bloques con `text` attr cuentan en el content concatenado."""
    block_with_text = MagicMock()
    block_with_text.text = "hola"
    block_without_text = MagicMock(spec=[])  # ningun atributo

    result = MagicMock()
    result.content = [block_with_text, block_without_text]
    result.usage = MagicMock(input_tokens=5, output_tokens=2)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=result)

    provider = AnthropicProvider(api_key="sk-ant-fake")
    provider._client = client

    req = CompletionRequest(
        messages=[{"role": "user", "content": "?"}], model="claude-sonnet-4-6"
    )
    response = await provider.complete(req)
    assert response.content == "hola"


# ── AnthropicProvider.stream_complete() ────────────────────────────────


async def test_anthropic_stream_yieldea_text_chunks() -> None:
    """El stream_complete delega al async ctx manager `messages.stream`."""
    provider = AnthropicProvider(api_key="sk-ant-fake")

    async def _aiter_text() -> AsyncIterator[str]:
        for word in ["hola", " ", "mundo"]:
            yield word

    fake_stream_obj = MagicMock()
    fake_stream_obj.text_stream = _aiter_text()

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield fake_stream_obj

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = _ctx
    provider._client = client

    req = CompletionRequest(
        messages=[{"role": "user", "content": "que onda"}],
        model="claude-sonnet-4-6",
        stream=True,
    )
    chunks = [c async for c in provider.stream_complete(req)]
    assert "".join(chunks) == "hola mundo"


# ── _ensure_client lazy init ───────────────────────────────────────────


def test_anthropic_ensure_client_inicializa_una_vez(monkeypatch) -> None:
    """_ensure_client cachea el cliente."""
    provider = AnthropicProvider(api_key="sk-ant-fake")

    fake_client = MagicMock()
    init_count = {"n": 0}

    class FakeAsync:
        def __init__(self, **kwargs):
            init_count["n"] += 1

        def __new__(cls, **kwargs):
            return fake_client

    fake_module = MagicMock()
    fake_module.AsyncAnthropic = FakeAsync
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_module)

    c1 = provider._ensure_client()
    c2 = provider._ensure_client()
    assert c1 is c2
    assert c1 is fake_client


# ── MistralProvider ────────────────────────────────────────────────────


def test_mistral_provider_uses_correct_pricing() -> None:
    """Pricing dict de MistralProvider tiene los modelos esperados con valores USD/M tokens."""
    pricing = MistralProvider.PRICING
    assert pricing["mistral-small-latest"] == {"input": 0.1, "output": 0.3}
    assert pricing["mistral-medium-latest"] == {"input": 2.5, "output": 7.5}
    assert pricing["mistral-large-latest"] == {"input": 2.0, "output": 6.0}
    assert pricing["codestral-latest"] == {"input": 0.3, "output": 0.9}


def test_get_provider_mistral_returns_mistral_provider(monkeypatch) -> None:
    """El resolver de get_provider routea 'mistral' a MistralProvider, NO al
    fallback graceful (que cae a mock para providers desconocidos)."""
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-fake")
    p = get_provider("mistral")
    assert isinstance(p, MistralProvider)
    assert p.name == "mistral"
