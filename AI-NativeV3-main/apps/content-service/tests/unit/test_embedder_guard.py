"""Tests del guard anti-embeddings-falsos (BUG-4).

Garantizan que NUNCA se indexe con vectores falsos (mock) creyendo que son
reales:
- en dev el mock es válido pero RUIDOSO (WARNING) y queda MARCADO;
- en producción resolver a mock es FATAL (RuntimeError), imposible indexar.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest
from content_service.embedding.embedder import (
    GeminiEmbedder,
    MockEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)
from content_service.models import Material
from content_service.services.ingestion import IngestionPipeline


@pytest.fixture(autouse=True)
def _clear_embedder_cache() -> Any:
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


def test_flag_is_semantic_distingue_mock_de_reales() -> None:
    # El mock NO es semántico; los embedders reales sí (atributo de clase,
    # no requiere instanciarlos).
    assert MockEmbedder.is_semantic is False
    assert GeminiEmbedder.is_semantic is True
    assert SentenceTransformerEmbedder.is_semantic is True


def test_get_embedder_mock_en_dev_warnea_pero_devuelve_mock(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EMBEDDER", "mock")
    monkeypatch.delenv("ENVIRONMENT", raising=False)  # default: development

    with caplog.at_level(logging.WARNING, logger="content_service.embedding.embedder"):
        embedder = get_embedder()

    assert isinstance(embedder, MockEmbedder)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "esperaba un WARNING claro al resolver a mock en dev"
    assert "NO-semántico" in warnings[0].getMessage()


@pytest.mark.parametrize("env", ["production", "prod", "staging"])
def test_get_embedder_mock_en_produccion_falla_fuerte(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("EMBEDDER", "mock")
    monkeypatch.setenv("ENVIRONMENT", env)

    with pytest.raises(RuntimeError, match="NO-semántico"):
        get_embedder()


def test_get_embedder_fallback_silencioso_falla_fuerte_en_prod(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso real del BUG-4: EMBEDDER sin setear + deps reales ausentes.

    Simulamos la ausencia de sentence-transformers forzando ImportError.
    """
    monkeypatch.delenv("EMBEDDER", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    import builtins

    real_import = builtins.__import__

    def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in ("sentence_transformers", "torch"):
            raise ImportError(f"forced: {name} not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match="fallback silencioso a mock"):
        get_embedder()


class _FakeSavepoint:
    """SAVEPOINT no-op para el `async with session.begin_nested()` del pipeline."""

    async def __aenter__(self) -> _FakeSavepoint:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeSession:
    """AsyncSession mínima para ejercitar el pipeline sin DB real."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def begin_nested(self) -> _FakeSavepoint:
        return _FakeSavepoint()


async def test_ingesta_con_mock_warnea_y_marca_los_chunks(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EMBEDDER", "mock")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    material = Material(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        materia_id=uuid.uuid4(),
        comision_id=None,
        tipo="markdown",
        nombre="guia.md",
        tamano_bytes=10,
        storage_path="x",
        estado="uploaded",
        uploaded_by=uuid.uuid4(),
    )
    content = (
        b"# Recursion\n\nLa recursion es cuando una funcion se llama a si misma. "
        b"Es un concepto fundamental que permite dividir un problema en "
        b"subproblemas mas chicos.\n"
    )
    session = _FakeSession()
    pipeline = IngestionPipeline(session)

    with caplog.at_level(
        logging.WARNING, logger="content_service.services.ingestion"
    ):
        result = await pipeline.ingest(material, content, "guia.md")

    # 1. Indexó pero deja el modo expuesto (no finge que es real).
    assert result.estado == "indexed"
    assert result.chunks_created >= 1
    assert result.is_semantic_embedding is False
    assert result.embedding_model == "mock-deterministic"

    # 2. WARNING claro al indexar con mock.
    ingest_warnings = [
        r
        for r in caplog.records
        if r.name == "content_service.services.ingestion"
        and r.levelno == logging.WARNING
    ]
    assert ingest_warnings, "esperaba WARNING al indexar con embedder mock"
    assert "FALSOS" in ingest_warnings[0].getMessage()

    # 3. Marcador durable persistido en cada chunk.
    assert session.added, "esperaba chunks persistidos"
    assert all(c.embedding_model == "mock-deterministic" for c in session.added)
