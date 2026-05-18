"""Tests del GovernanceClient (apps/tutor-service/.../services/governance_client.py)."""

from __future__ import annotations

import httpx
import pytest
import respx
from tutor_service.services.governance_client import (
    ActivePrompt,
    GovernanceClient,
)

BASE_URL = "http://governance:8010"


@pytest.mark.asyncio
@respx.mock
async def test_load_prompt_returns_active_prompt() -> None:
    respx.get(f"{BASE_URL}/api/v1/prompts/tutor/v1.0.1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "tutor",
                "version": "v1.0.1",
                "content": "# system prompt\n...",
                "hash": "sha256-abc123",
            },
        )
    )
    client = GovernanceClient(BASE_URL)

    prompt = await client.load_prompt("tutor", "v1.0.1")

    assert isinstance(prompt, ActivePrompt)
    assert prompt.name == "tutor"
    assert prompt.version == "v1.0.1"
    assert prompt.hash == "sha256-abc123"
    assert "# system prompt" in prompt.content


@pytest.mark.asyncio
@respx.mock
async def test_load_prompt_404_raises() -> None:
    respx.get(f"{BASE_URL}/api/v1/prompts/tutor/v9.9.9").mock(
        return_value=httpx.Response(404, text="not found")
    )
    client = GovernanceClient(BASE_URL)

    with pytest.raises(httpx.HTTPStatusError):
        await client.load_prompt("tutor", "v9.9.9")


@pytest.mark.asyncio
@respx.mock
async def test_active_configs_returns_dict() -> None:
    respx.get(f"{BASE_URL}/api/v1/active_configs").mock(
        return_value=httpx.Response(
            200,
            json={
                "active": {
                    "default": {"tutor": "v1.0.1"},
                    "tenant-x": {"tutor": "v1.1.0"},
                }
            },
        )
    )
    client = GovernanceClient(BASE_URL)

    configs = await client.active_configs()

    assert configs["active"]["default"]["tutor"] == "v1.0.1"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_for_tenant_uses_default_when_no_override() -> None:
    respx.get(f"{BASE_URL}/api/v1/active_configs").mock(
        return_value=httpx.Response(
            200,
            json={"active": {"default": {"tutor": "v1.0.1"}}},
        )
    )
    respx.get(f"{BASE_URL}/api/v1/prompts/tutor/v1.0.1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "tutor",
                "version": "v1.0.1",
                "content": "x",
                "hash": "h",
            },
        )
    )
    client = GovernanceClient(BASE_URL)

    prompt = await client.resolve_for_tenant("any-tenant")

    assert prompt.version == "v1.0.1"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_for_tenant_uses_override_when_present() -> None:
    respx.get(f"{BASE_URL}/api/v1/active_configs").mock(
        return_value=httpx.Response(
            200,
            json={
                "active": {
                    "default": {"tutor": "v1.0.1"},
                    "tenant-special": {"tutor": "v1.1.0"},
                }
            },
        )
    )
    respx.get(f"{BASE_URL}/api/v1/prompts/tutor/v1.1.0").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "tutor",
                "version": "v1.1.0",
                "content": "x",
                "hash": "h2",
            },
        )
    )
    client = GovernanceClient(BASE_URL)

    prompt = await client.resolve_for_tenant("tenant-special")

    assert prompt.version == "v1.1.0"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_for_tenant_raises_when_no_active_version() -> None:
    respx.get(f"{BASE_URL}/api/v1/active_configs").mock(
        return_value=httpx.Response(200, json={"active": {}})
    )
    client = GovernanceClient(BASE_URL)

    with pytest.raises(RuntimeError, match="No hay versión activa"):
        await client.resolve_for_tenant("any-tenant")
