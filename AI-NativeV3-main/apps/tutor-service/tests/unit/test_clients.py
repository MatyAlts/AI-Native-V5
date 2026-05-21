"""Tests de los clients agrupados en apps/tutor-service/.../services/clients.py.

Cubre las 4 clases: GovernanceClient, ContentClient, AIGatewayClient, CTRClient.
NOTA: hay duplicación con `governance_client.py` y `content_client.py` (deuda
documentada en code review pre-defensa). Estos tests cubren el archivo `clients.py`.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx
from tutor_service.services.clients import (
    AIGatewayClient,
    ContentClient,
    CTRClient,
    GovernanceClient,
)

GOV = "http://governance:8010"
CONTENT = "http://content:8009"
AI_GW = "http://ai-gateway:8011"
CTR = "http://ctr:8007"


# ---------- GovernanceClient ----------


@pytest.mark.asyncio
@respx.mock
async def test_governance_get_prompt() -> None:
    respx.get(f"{GOV}/api/v1/prompts/tutor/v1.0.0").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "tutor",
                "version": "v1.0.0",
                "content": "p",
                "hash": "h",
            },
        )
    )
    client = GovernanceClient(GOV)
    cfg = await client.get_prompt("tutor", "v1.0.0")
    assert cfg.version == "v1.0.0"
    assert cfg.hash == "h"


@pytest.mark.asyncio
@respx.mock
async def test_governance_get_active_configs() -> None:
    respx.get(f"{GOV}/api/v1/active_configs").mock(
        return_value=httpx.Response(200, json={"active": {"default": {}}})
    )
    client = GovernanceClient(GOV)
    out = await client.get_active_configs()
    assert "active" in out


# ---------- ContentClient ----------


@pytest.mark.asyncio
@respx.mock
async def test_content_retrieve_success() -> None:
    respx.post(f"{CONTENT}/api/v1/retrieve").mock(
        return_value=httpx.Response(
            200,
            json={
                "chunks": [
                    {
                        "id": str(uuid4()),
                        "contenido": "x",
                        "material_nombre": "m",
                        "score_rerank": 0.9,
                    }
                ],
                "chunks_used_hash": "hh",
                "latency_ms": 12.0,
            },
        )
    )
    client = ContentClient(CONTENT)
    res = await client.retrieve(
        query="q",
        comision_id=uuid4(),
        top_k=5,
        tenant_id=uuid4(),
        caller_id=uuid4(),
    )
    assert len(res.chunks) == 1
    assert res.chunks_used_hash == "hh"


@pytest.mark.asyncio
@respx.mock
async def test_content_retrieve_propagates_caller_id() -> None:
    captured: dict = {}

    def cap(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return httpx.Response(
            200,
            json={
                "chunks": [],
                "chunks_used_hash": "h",
                "latency_ms": 1.0,
            },
        )

    respx.post(f"{CONTENT}/api/v1/retrieve").mock(side_effect=cap)

    caller_id = uuid4()
    tenant_id = uuid4()
    client = ContentClient(CONTENT)
    await client.retrieve(
        query="q",
        comision_id=uuid4(),
        top_k=3,
        tenant_id=tenant_id,
        caller_id=caller_id,
    )
    assert captured["headers"]["x-user-id"] == str(caller_id)
    assert captured["headers"]["x-tenant-id"] == str(tenant_id)


# ---------- AIGatewayClient ----------


@pytest.mark.asyncio
@respx.mock
async def test_ai_gateway_stream_yields_tokens() -> None:
    # Backlog QA 2026-05-07: el endpoint emite `done` con provider+tokens
    # cuando esta disponible (gap auditoria doctoral). Los probamos en
    # otro test (`test_ai_gateway_stream_yields_usage_event`).
    sse_body = (
        b'data: {"type":"token","content":"hola "}\n\n'
        b'data: {"type":"token","content":"mundo"}\n\n'
        b'data: {"type":"done"}\n\n'
    )
    respx.post(f"{AI_GW}/api/v1/stream").mock(
        return_value=httpx.Response(
            200, content=sse_body, headers={"Content-Type": "text/event-stream"}
        )
    )
    client = AIGatewayClient(AI_GW)
    events: list[dict] = []
    async for ev in client.stream(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-mock",
        tenant_id=uuid4(),
    ):
        events.append(ev)
    # `done` sin provider/tokens no produce evento `usage` (compat con
    # ai-gateway viejo).
    assert events == [
        {"type": "chunk", "content": "hola "},
        {"type": "chunk", "content": "mundo"},
    ]


@pytest.mark.asyncio
@respx.mock
async def test_ai_gateway_stream_yields_usage_event() -> None:
    """Backlog QA 2026-05-07: cuando el ai-gateway expone `provider`,
    `tokens_input`, `tokens_output` en el `done` event SSE, el client los
    proyecta como un dict {"type":"usage", ...} para que el tutor-service
    los pueda persistir en el payload de `tutor_respondio` (auditoria
    doctoral de costos de LLM cross-evento).
    """
    sse_body = (
        b'data: {"type":"token","content":"foo"}\n\n'
        b'data: {"type":"done","provider":"anthropic","tokens_input":42,'
        b'"tokens_output":15,"estimated_cost_usd":0.0007}\n\n'
    )
    respx.post(f"{AI_GW}/api/v1/stream").mock(
        return_value=httpx.Response(
            200, content=sse_body, headers={"Content-Type": "text/event-stream"}
        )
    )
    client = AIGatewayClient(AI_GW)
    events: list[dict] = []
    async for ev in client.stream(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-sonnet-4-6",
        tenant_id=uuid4(),
    ):
        events.append(ev)
    assert events == [
        {"type": "chunk", "content": "foo"},
        {
            "type": "usage",
            "provider": "anthropic",
            "tokens_input": 42,
            "tokens_output": 15,
            "cost_usd": 0.0007,
        },
    ]


@pytest.mark.asyncio
@respx.mock
async def test_ai_gateway_stream_raises_on_error_event() -> None:
    sse_body = b'data: {"type":"error","message":"budget exceeded"}\n\n'
    respx.post(f"{AI_GW}/api/v1/stream").mock(
        return_value=httpx.Response(
            200, content=sse_body, headers={"Content-Type": "text/event-stream"}
        )
    )
    client = AIGatewayClient(AI_GW)
    with pytest.raises(RuntimeError, match="budget exceeded"):
        async for _ in client.stream(
            messages=[{"role": "user", "content": "x"}],
            model="m",
            tenant_id=uuid4(),
        ):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_ai_gateway_stream_skips_invalid_lines() -> None:
    sse_body = (
        b"event: ping\n\n"
        b"data: not-json\n\n"
        b'data: {"type":"token","content":"ok"}\n\n'
    )
    respx.post(f"{AI_GW}/api/v1/stream").mock(
        return_value=httpx.Response(
            200, content=sse_body, headers={"Content-Type": "text/event-stream"}
        )
    )
    client = AIGatewayClient(AI_GW)
    out: list[dict] = []
    async for c in client.stream(
        messages=[{"role": "user", "content": "x"}],
        model="m",
        tenant_id=uuid4(),
    ):
        out.append(c)
    assert out == [{"type": "chunk", "content": "ok"}]


# ---------- CTRClient ----------


@pytest.mark.asyncio
@respx.mock
async def test_ctr_publish_event_returns_message_id() -> None:
    respx.post(f"{CTR}/api/v1/events").mock(
        return_value=httpx.Response(200, json={"message_id": "1234-0"})
    )
    client = CTRClient(CTR)
    mid = await client.publish_event(
        event={"type": "x", "payload": {}},
        tenant_id=uuid4(),
        caller_id=uuid4(),
    )
    assert mid == "1234-0"


@pytest.mark.asyncio
@respx.mock
async def test_ctr_get_episode_returns_data() -> None:
    eid = uuid4()
    respx.get(f"{CTR}/api/v1/episodes/{eid}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": str(eid),
                "tenant_id": str(uuid4()),
                "events": [],
            },
        )
    )
    client = CTRClient(CTR)
    data = await client.get_episode(
        episode_id=eid, tenant_id=uuid4(), caller_id=uuid4()
    )
    assert data is not None
    assert data["id"] == str(eid)


@pytest.mark.asyncio
@respx.mock
async def test_ctr_get_episode_returns_none_on_404() -> None:
    eid = uuid4()
    respx.get(f"{CTR}/api/v1/episodes/{eid}").mock(
        return_value=httpx.Response(404)
    )
    client = CTRClient(CTR)
    data = await client.get_episode(
        episode_id=eid, tenant_id=uuid4(), caller_id=uuid4()
    )
    assert data is None


@pytest.mark.asyncio
@respx.mock
async def test_ctr_get_episode_raises_on_5xx() -> None:
    eid = uuid4()
    respx.get(f"{CTR}/api/v1/episodes/{eid}").mock(
        return_value=httpx.Response(500)
    )
    client = CTRClient(CTR)
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_episode(
            episode_id=eid, tenant_id=uuid4(), caller_id=uuid4()
        )
