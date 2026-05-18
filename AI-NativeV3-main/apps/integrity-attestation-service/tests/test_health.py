"""Tests del endpoint /health del integrity-attestation-service."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from integrity_attestation_service.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _patch_paths(log_dir: Path, key_path: Path) -> Any:
    return [
        patch(
            "integrity_attestation_service.routes.health.settings.attestation_log_dir",
            log_dir,
        ),
        patch(
            "integrity_attestation_service.routes.health.settings.attestation_private_key_path",
            key_path,
        ),
    ]


async def test_health_ready_all_ok(tmp_path: Path, client: AsyncClient) -> None:
    log_dir = tmp_path / "attestations"
    log_dir.mkdir()
    key_path = tmp_path / "private.pem"
    key_path.write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----")
    patches = _patch_paths(log_dir, key_path)
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "integrity-attestation-service"
    assert body["status"] == "ready"
    assert set(body["checks"].keys()) == {
        "attestation_dir_writable",
        "private_key_readable",
    }


async def test_health_ready_dir_missing(tmp_path: Path, client: AsyncClient) -> None:
    log_dir = tmp_path / "missing"  # not created
    key_path = tmp_path / "private.pem"
    key_path.write_text("fake key")
    patches = _patch_paths(log_dir, key_path)
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"]["attestation_dir_writable"]["ok"] is False


async def test_health_ready_key_missing(tmp_path: Path, client: AsyncClient) -> None:
    log_dir = tmp_path / "attestations"
    log_dir.mkdir()
    key_path = tmp_path / "missing.pem"  # not created
    patches = _patch_paths(log_dir, key_path)
    for p in patches:
        p.start()
    try:
        response = await client.get("/health/ready")
    finally:
        for p in patches:
            p.stop()
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"]["private_key_readable"]["ok"] is False


async def test_health_live(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_root(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "integrity-attestation-service"
    assert data["adr"] == "ADR-021"
