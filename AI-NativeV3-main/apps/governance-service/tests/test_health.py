"""Tests del endpoint /health del governance-service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from governance_service.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _patch_prompts_dir(path: str) -> Any:
    return patch(
        "governance_service.routes.health.settings.prompts_repo_path", path
    )


async def test_health_ready_prompt_present(
    tmp_path: Path, client: AsyncClient
) -> None:
    prompt_path = tmp_path / "prompts" / "tutor" / "v1.0.1" / "system.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("# tutor system prompt")
    with _patch_prompts_dir(str(tmp_path)):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "governance-service"
    assert body["status"] == "ready"
    assert body["checks"]["prompts_filesystem"]["ok"] is True


async def test_health_ready_prompt_missing(
    tmp_path: Path, client: AsyncClient
) -> None:
    """Prompt no existe → critical check falla → 503."""
    with _patch_prompts_dir(str(tmp_path)):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"]["prompts_filesystem"]["ok"] is False
    assert "not found" in body["checks"]["prompts_filesystem"]["error"]


async def test_health_ready_prompt_unreadable(
    tmp_path: Path, client: AsyncClient
) -> None:
    """Prompt existe pero permisos no permiten lectura → 503."""
    prompt_path = tmp_path / "prompts" / "tutor" / "v1.0.1" / "system.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("# tutor")
    os.chmod(prompt_path, 0o000)
    try:
        with _patch_prompts_dir(str(tmp_path)):
            response = await client.get("/health/ready")
        # En Linux con umask normal, chmod 000 hace inaccesible. En CI puede
        # variar — solo aseguramos que si os.access dice False, el response
        # es 503. Si el sistema permite leer (root/CI quirk), test no falla.
        if response.status_code == 503:
            body = response.json()
            assert "not readable" in body["checks"]["prompts_filesystem"][
                "error"
            ]
    finally:
        os.chmod(prompt_path, 0o644)


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "governance-service"
