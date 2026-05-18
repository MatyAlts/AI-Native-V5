"""Tests del ContentClient (apps/tutor-service/.../services/content_client.py)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx
from tutor_service.services.content_client import (
    ContentClient,
    RetrievalResult,
)

BASE_URL = "http://content:8009"


def _payload(chunks: int = 2) -> dict:
    return {
        "chunks": [
            {
                "id": str(uuid4()),
                "contenido": f"chunk {i} contenido",
                "material_id": str(uuid4()),
                "material_nombre": f"material-{i}",
                "position": i,
                "chunk_type": "text",
                "score_rerank": 0.9 - i * 0.1,
                "score_vector": 0.8 - i * 0.1,
                "meta": {"source": "test"},
            }
            for i in range(chunks)
        ],
        "chunks_used_hash": "abc123def456",
        "latency_ms": 42.5,
        "rerank_applied": True,
    }


@pytest.mark.asyncio
@respx.mock
async def test_retrieve_returns_chunks_and_hash() -> None:
    route = respx.post(f"{BASE_URL}/api/v1/retrieve").mock(
        return_value=httpx.Response(200, json=_payload(chunks=3))
    )
    client = ContentClient(BASE_URL)

    result = await client.retrieve(
        query="qué es un puntero",
        comision_id=uuid4(),
        tenant_id=uuid4(),
    )

    assert route.called
    assert isinstance(result, RetrievalResult)
    assert len(result.chunks) == 3
    assert result.chunks_used_hash == "abc123def456"
    assert result.latency_ms == 42.5
    assert result.rerank_applied is True


@pytest.mark.asyncio
@respx.mock
async def test_retrieve_propagates_service_account_headers() -> None:
    captured: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content
        return httpx.Response(200, json=_payload())

    respx.post(f"{BASE_URL}/api/v1/retrieve").mock(side_effect=_capture)

    tenant_id = uuid4()
    client = ContentClient(BASE_URL)
    await client.retrieve(query="x", comision_id=uuid4(), tenant_id=tenant_id)

    assert captured["headers"]["x-tenant-id"] == str(tenant_id)
    assert captured["headers"]["x-user-roles"] == "tutor_service"
    assert (
        captured["headers"]["x-user-id"]
        == "00000000-0000-0000-0000-000000000099"
    )


@pytest.mark.asyncio
@respx.mock
async def test_retrieve_raises_on_http_error() -> None:
    respx.post(f"{BASE_URL}/api/v1/retrieve").mock(
        return_value=httpx.Response(500, text="server error")
    )
    client = ContentClient(BASE_URL)

    with pytest.raises(httpx.HTTPStatusError):
        await client.retrieve(
            query="x", comision_id=uuid4(), tenant_id=uuid4()
        )


@pytest.mark.asyncio
@respx.mock
async def test_retrieve_handles_missing_optional_fields() -> None:
    """score_rerank y meta son opcionales en el payload."""
    payload = _payload(chunks=1)
    del payload["chunks"][0]["score_rerank"]
    del payload["chunks"][0]["meta"]
    payload["rerank_applied"] = False

    respx.post(f"{BASE_URL}/api/v1/retrieve").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = ContentClient(BASE_URL)

    result = await client.retrieve(
        query="x", comision_id=uuid4(), tenant_id=uuid4()
    )

    assert result.chunks[0].score_rerank is None
    assert result.chunks[0].meta == {}
    assert result.rerank_applied is False
