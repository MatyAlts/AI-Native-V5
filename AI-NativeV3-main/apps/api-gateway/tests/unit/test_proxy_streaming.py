"""Tests del forwarding del proxy: streaming (SSE) vs buffered.

Verifican el fix del bug P-1: para respuestas `text/event-stream` (el tutor
socrático) el gateway reenvía los chunks a medida que llegan (`aiter_raw`) en
vez de bufferear el body entero (`aread`). Para respuestas no-streaming se
mantiene el forward buffered histórico.

Se monta sólo el `proxy.router` en una app FastAPI pelada (sin el
JWTMiddleware) para aislar la lógica de forwarding, y se parchea
`httpx.AsyncClient` con un doble que expone si el body se buffereó.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api_gateway.routes import proxy


class _FakeUpstream:
    """Respuesta upstream falsa que registra si se buffereó (`aread`)."""

    def __init__(
        self, chunks: list[bytes], content_type: str, status_code: int = 200
    ) -> None:
        self._chunks = chunks
        self.headers = httpx.Headers({"content-type": content_type})
        self.status_code = status_code
        self.aread_called = False
        self.aiter_raw_called = False
        self.aclose_called = False
        self._content = b""

    async def aiter_raw(self):
        self.aiter_raw_called = True
        for chunk in self._chunks:
            yield chunk

    async def aread(self) -> bytes:
        self.aread_called = True
        self._content = b"".join(self._chunks)
        return self._content

    @property
    def content(self) -> bytes:
        return b"".join(self._chunks)

    async def aclose(self) -> None:
        self.aclose_called = True


class _FakeClient:
    def __init__(self, upstream: _FakeUpstream) -> None:
        self._upstream = upstream
        self.closed = False

    def build_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return ("fake-request", args, kwargs)

    async def send(self, request, stream: bool = False):  # noqa: ANN001
        return self._upstream

    async def aclose(self) -> None:
        self.closed = True


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(proxy.router)
    return app


async def _call(method: str, path: str, upstream: _FakeUpstream, **kwargs):
    fake_client = _FakeClient(upstream)
    with patch.object(proxy.httpx, "AsyncClient", return_value=fake_client):
        transport = ASGITransport(app=_app())
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.request(method, path, **kwargs)
    return resp, fake_client


@pytest.mark.asyncio
async def test_streaming_response_no_se_bufferea() -> None:
    """Respuesta SSE: se reenvía chunk-a-chunk, nunca se llama `aread`."""
    chunks = [b"data: uno\n\n", b"data: dos\n\n", b"data: tres\n\n"]
    upstream = _FakeUpstream(chunks, "text/event-stream; charset=utf-8")

    resp, fake_client = await _call(
        "POST",
        "/api/v1/episodes/11111111-1111-1111-1111-111111111111/message",
        upstream,
        content=b'{"content":"hola"}',
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.content == b"".join(chunks)
    # La prueba dura del fix P-1: el path streaming usó aiter_raw y NUNCA
    # buffereó el body entero con aread.
    assert upstream.aiter_raw_called is True
    assert upstream.aread_called is False
    # Recursos liberados al terminar el stream.
    assert upstream.aclose_called is True
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_non_streaming_response_se_bufferea() -> None:
    """Respuesta JSON normal: forward buffered histórico (usa `aread`)."""
    upstream = _FakeUpstream([b'{"ok":true}'], "application/json")

    resp, fake_client = await _call("GET", "/api/v1/materias", upstream)

    assert resp.status_code == 200
    assert resp.content == b'{"ok":true}'
    assert upstream.aread_called is True
    assert upstream.aiter_raw_called is False
    assert upstream.aclose_called is True
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_hop_by_hop_headers_no_se_propagan() -> None:
    """content-length / transfer-encoding / connection se filtran del upstream."""
    upstream = _FakeUpstream([b"data: x\n\n"], "text/event-stream")
    upstream.headers = httpx.Headers(
        {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            "content-length": "9",
            "transfer-encoding": "chunked",
            "connection": "keep-alive",
        }
    )

    resp, _ = await _call(
        "POST",
        "/api/v1/episodes/22222222-2222-2222-2222-222222222222/message",
        upstream,
        content=b"{}",
    )

    assert resp.status_code == 200
    # cache-control (relevante para SSE) se preserva.
    assert resp.headers.get("cache-control") == "no-cache"
    # transfer-encoding: httpx/ASGI re-setea el real, no el del upstream.
    assert "keep-alive" not in resp.headers.get("connection", "")
