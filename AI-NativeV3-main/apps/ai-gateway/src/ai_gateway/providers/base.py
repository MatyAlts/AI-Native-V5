"""Providers de LLM con interfaz común.

El ai-gateway expone una API unificada independiente del proveedor
underlying. Cada provider implementa BaseProvider. El mock provider
se usa en tests para evitar pagar API calls reales.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass
class CompletionRequest:
    messages: list[dict[str, str]]  # [{"role": "user"|"assistant"|"system", "content": "..."}]
    model: str
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    response_format: dict[str, str] | None = None


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool = False


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abstractmethod
    def stream_complete(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Async generator que yieldea chunks de texto."""
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Provider determinista para tests. No hace llamadas externas."""

    name = "mock"

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        # Extraer la última user message
        user_messages = [m for m in request.messages if m.get("role") == "user"]
        last = user_messages[-1]["content"] if user_messages else ""
        response_text = f"[mock respuesta para: {last[:50]}]"
        return CompletionResponse(
            content=response_text,
            model=request.model,
            provider="mock",
            input_tokens=sum(len(m.get("content", "")) for m in request.messages) // 4,
            output_tokens=len(response_text) // 4,
            cost_usd=0.0,
        )

    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Yieldea palabra por palabra para simular streaming."""
        response = await self.complete(request)
        for word in response.content.split():
            yield word + " "


class AnthropicProvider(BaseProvider):
    """Provider real de Anthropic (Sonnet/Haiku/Opus)."""

    name = "anthropic"

    # Precios estimados USD por 1M tokens (abril 2026)
    PRICING = {
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
        "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    }

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        client = self._ensure_client()

        # Separar system de messages
        system_msgs = [m["content"] for m in request.messages if m.get("role") == "system"]
        conversation = [m for m in request.messages if m.get("role") != "system"]

        result = await client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system="\n\n".join(system_msgs) if system_msgs else "",
            messages=conversation,
        )

        content = "".join(block.text for block in result.content if hasattr(block, "text"))
        input_tok = result.usage.input_tokens
        output_tok = result.usage.output_tokens
        pricing = self.PRICING.get(request.model, {"input": 1.0, "output": 5.0})
        cost = (input_tok * pricing["input"] + output_tok * pricing["output"]) / 1_000_000

        return CompletionResponse(
            content=content,
            model=request.model,
            provider="anthropic",
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
        )

    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[str]:
        client = self._ensure_client()
        system_msgs = [m["content"] for m in request.messages if m.get("role") == "system"]
        conversation = [m for m in request.messages if m.get("role") != "system"]

        async with client.messages.stream(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system="\n\n".join(system_msgs) if system_msgs else "",
            messages=conversation,
        ) as stream:
            async for text in stream.text_stream:
                yield text


class MistralProvider(BaseProvider):
    """Provider de Mistral AI (mistral-small, mistral-medium, mistral-large, codestral)."""

    name = "mistral"

    PRICING = {
        "mistral-small-latest": {"input": 0.1, "output": 0.3},
        "mistral-medium-latest": {"input": 2.5, "output": 7.5},
        "mistral-large-latest": {"input": 2.0, "output": 6.0},
        "codestral-latest": {"input": 0.3, "output": 0.9},
    }

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from mistralai import Mistral

            self._client = Mistral(api_key=self.api_key)
        return self._client

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        client = self._ensure_client()

        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            kwargs["response_format"] = request.response_format

        result = await client.chat.complete_async(**kwargs)

        choice = result.choices[0]
        content = choice.message.content or ""
        input_tok = result.usage.prompt_tokens
        output_tok = result.usage.completion_tokens
        pricing = self.PRICING.get(request.model, {"input": 1.0, "output": 3.0})
        cost = (input_tok * pricing["input"] + output_tok * pricing["output"]) / 1_000_000

        return CompletionResponse(
            content=content,
            model=request.model,
            provider="mistral",
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
        )

    async def stream_complete(self, request: CompletionRequest) -> AsyncIterator[str]:
        client = self._ensure_client()

        result = await client.chat.stream_async(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        async for event in result:
            chunk = event.data.choices[0].delta.content
            if chunk:
                yield chunk


@lru_cache(maxsize=1)
def get_provider(name: str = "") -> BaseProvider:
    """Factory de providers. name='mock' para tests.

    Resolución de provider:
        1. Argumento explícito `name` (tests) — si es desconocido, raise ValueError.
        2. Env var `LLM_PROVIDER` (override de runtime) — si es desconocido,
           log warning + fallback a mock (para no tirar 502 en dev cuando el
           `.env` del usuario apunta a un provider no implementado todavía,
           ej. `mistral`/`gemini` que están DEFERIDOS por epic ai-native-completion).
        3. `Settings.llm_provider` (default `mock`, ver CLAUDE.md) — mismo
           comportamiento que (2): unknown → warning + mock.
    """
    if name:
        which = name.lower()
        from_runtime_config = False
    elif "LLM_PROVIDER" in os.environ:
        which = os.environ["LLM_PROVIDER"].lower()
        from_runtime_config = True
    else:
        # Import diferido: evita ciclo si tests parchean settings antes de importar.
        from ai_gateway.config import settings

        which = settings.llm_provider.lower()
        from_runtime_config = True
    if which == "mock":
        return MockProvider()
    if which == "anthropic":
        return AnthropicProvider()
    if which == "mistral":
        return MistralProvider()
    if from_runtime_config:
        import logging

        logging.getLogger(__name__).warning(
            "Provider '%s' desconocido o no implementado todavía; cayendo a mock. "
            "Setear LLM_PROVIDER=mock explícitamente para silenciar este warning.",
            which,
        )
        return MockProvider()
    raise ValueError(f"Provider desconocido: {which}")
