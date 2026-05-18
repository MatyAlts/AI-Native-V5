"""Tests del embedder mock."""

from __future__ import annotations

import pytest
from content_service.embedding.embedder import EMBEDDING_DIM, MockEmbedder


@pytest.fixture
def embedder() -> MockEmbedder:
    return MockEmbedder()


async def test_es_determinista(embedder: MockEmbedder) -> None:
    """Mismo texto produce el mismo vector."""
    v1 = await embedder.embed_query("qué es recursión?")
    v2 = await embedder.embed_query("qué es recursión?")
    assert v1 == v2


async def test_textos_distintos_producen_vectores_distintos(
    embedder: MockEmbedder,
) -> None:
    v1 = await embedder.embed_query("qué es recursión?")
    v2 = await embedder.embed_query("cómo funciona una iteración?")
    assert v1 != v2


async def test_dimension_correcta(embedder: MockEmbedder) -> None:
    vec = await embedder.embed_query("test")
    assert len(vec) == EMBEDDING_DIM


async def test_vector_normalizado(embedder: MockEmbedder) -> None:
    """Los vectores están normalizados (norma ~1)."""
    vec = await embedder.embed_query("test")
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


async def test_batch_de_documentos(embedder: MockEmbedder) -> None:
    texts = ["uno", "dos", "tres"]
    vectors = await embedder.embed_documents(texts)
    assert len(vectors) == 3
    assert all(len(v) == EMBEDDING_DIM for v in vectors)
    # Todos distintos
    assert vectors[0] != vectors[1]
    assert vectors[1] != vectors[2]
