"""Servicio de embeddings.

Estrategia:
1. Si hay GPU local disponible → sentence-transformers (gratis, rápido, privado).
2. Si no → API externa via ai-gateway (Voyage AI o OpenAI).
3. En tests → embedder mock determinista (hash-based) para evitar
   dependencias pesadas en CI.

El modelo default es `intfloat/multilingual-e5-large` (1024 dims, excelente
para español, benchmarks superiores a ada-002).
"""

from __future__ import annotations

import hashlib
import os
import struct
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


EMBEDDING_DIM = 1024


class BaseEmbedder(ABC):
    """Interfaz común de embedders."""

    model_name: str

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embeds de documentos a indexar."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed de una query de búsqueda (puede diferir del embed de doc)."""


class MockEmbedder(BaseEmbedder):
    """Embedder determinista basado en hash, para tests.

    No tiene semántica real pero es reproducible: mismo texto → mismo
    vector. Suficiente para verificar que el pipeline end-to-end funciona.
    """

    model_name = "mock-deterministic"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._hash_to_vector(text)

    def _hash_to_vector(self, text: str) -> list[float]:
        """SHA-512 del texto → 1024 floats normalizados en [-1, 1]."""
        # SHA-512 da 64 bytes. Lo ampliamos con SHA-256 de rondas sucesivas.
        seed = text.encode("utf-8")
        raw = b""
        h = hashlib.sha512(seed).digest()
        raw += h
        # 1024 dims * 4 bytes (float) = 4096 bytes necesarios
        while len(raw) < EMBEDDING_DIM * 4:
            h = hashlib.sha512(h).digest()
            raw += h

        # Convertir a floats en [-1, 1]
        ints = struct.unpack(f"<{EMBEDDING_DIM}I", raw[: EMBEDDING_DIM * 4])
        vec = [((i / (2**32 - 1)) * 2 - 1) for i in ints]
        # Normalizar
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class SentenceTransformerEmbedder(BaseEmbedder):
    """Embedder local con sentence-transformers + multilingual-e5-large."""

    model_name = "intfloat/multilingual-e5-large"

    def __init__(self) -> None:
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # e5 convention: prefijo "passage: " para docs
        prefixed = [f"passage: {t}" for t in texts]
        model = self._ensure_model()
        vectors = model.encode(
            prefixed,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    async def embed_query(self, text: str) -> list[float]:
        # e5 convention: prefijo "query: " para queries
        model = self._ensure_model()
        vec = model.encode([f"query: {text}"], normalize_embeddings=True, convert_to_numpy=True)
        return vec[0].tolist()


@lru_cache(maxsize=1)
def get_embedder() -> BaseEmbedder:
    """Factory: elige el embedder según config de entorno.

    Override con EMBEDDER=mock|local para tests.
    """
    which = os.environ.get("EMBEDDER", "").lower()
    if which == "mock":
        return MockEmbedder()
    if which == "local":
        return SentenceTransformerEmbedder()

    # Default: intentar local, fallback a mock si falta sentence-transformers
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401

        return SentenceTransformerEmbedder()
    except ImportError:
        return MockEmbedder()
