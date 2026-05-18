"""Tests del MockProvider."""

from __future__ import annotations

from ai_gateway.providers.base import CompletionRequest, MockProvider


async def test_mock_responde_deterministico() -> None:
    provider = MockProvider()
    req = CompletionRequest(
        messages=[{"role": "user", "content": "hola"}],
        model="claude-sonnet-4-6",
        temperature=0.0,
    )
    r1 = await provider.complete(req)
    r2 = await provider.complete(req)
    assert r1.content == r2.content
    assert r1.provider == "mock"
    assert r1.cost_usd == 0.0


async def test_mock_incluye_query_en_respuesta() -> None:
    provider = MockProvider()
    req = CompletionRequest(
        messages=[{"role": "user", "content": "pregunta original"}],
        model="claude-sonnet-4-6",
    )
    response = await provider.complete(req)
    assert "pregunta original" in response.content


async def test_mock_streaming_yieldea_chunks() -> None:
    provider = MockProvider()
    req = CompletionRequest(
        messages=[{"role": "user", "content": "test"}],
        model="claude-sonnet-4-6",
        stream=True,
    )
    chunks = []
    async for chunk in provider.stream_complete(req):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)
