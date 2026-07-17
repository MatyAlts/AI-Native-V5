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

import asyncio
import hashlib
import logging
import os
import struct
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024

# Entornos donde indexar/consultar con embeddings falsos (mock) es un error
# fatal: nunca queremos retrieval basura sirviendo tráfico real. `environment`
# del content-service (config.py) se alimenta de la env var ENVIRONMENT.
_NON_DEV_ENVIRONMENTS = frozenset({"production", "prod", "staging"})


class BaseEmbedder(ABC):
    """Interfaz común de embedders."""

    model_name: str
    # ¿El embedder produce vectores semánticos reales (True) o falsos —
    # deterministas por hash — (False)? El pipeline de ingesta usa esta bandera
    # para NO indexar embeddings falsos como si fueran reales (BUG-4).
    is_semantic: bool = True

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
    is_semantic = False

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


class GeminiEmbedder(BaseEmbedder):
    """Embedder via Google Gemini REST API (text-embedding-004).

    Usa httpx directo contra la REST API v1beta para evitar problemas
    de compatibilidad del SDK google-genai con versiones de API.
    """

    model_name = "gemini-embedding-001"

    def __init__(self) -> None:
        import httpx

        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            msg = "GEMINI_API_KEY env var is required for GeminiEmbedder"
            raise ValueError(msg)
        self._http = httpx.AsyncClient(timeout=30)
        self._url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:embedContent"

    def _pad(self, vector: list[float]) -> list[float]:
        if len(vector) >= EMBEDDING_DIM:
            return vector[:EMBEDDING_DIM]
        return vector + [0.0] * (EMBEDDING_DIM - len(vector))

    async def _embed_one(self, text: str, task_type: str) -> list[float]:
        resp = await self._http.post(
            self._url,
            params={"key": self._api_key},
            json={"model": f"models/{self.model_name}", "content": {"parts": [{"text": text}]}, "taskType": task_type},
        )
        resp.raise_for_status()
        values = resp.json()["embedding"]["values"]
        return self._pad(values)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self._embed_one(t, "RETRIEVAL_DOCUMENT") for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed_one(text, "RETRIEVAL_QUERY")


class SentenceTransformerEmbedder(BaseEmbedder):
    """Embedder local con sentence-transformers + multilingual-e5-large."""

    model_name = "intfloat/multilingual-e5-large"

    def __init__(self) -> None:
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            # EasyPanel: forzamos CPU para evitar dependencia de runtime GPU/NVIDIA.
            device = "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # e5 convention: prefijo "passage: " para docs
        prefixed = [f"passage: {t}" for t in texts]
        # sentence-transformers.encode() es CPU-bound (P-10/A2.9): corre en un
        # thread para NO bloquear el event loop del servicio async. El resultado
        # (los embeddings) es idéntico — solo cambia dónde se computa.
        return await asyncio.to_thread(self._encode_documents_sync, prefixed)

    def _encode_documents_sync(self, prefixed: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            prefixed,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    async def embed_query(self, text: str) -> list[float]:
        # Idem embed_documents: el cómputo CPU-bound va a un thread (P-10/A2.9).
        return await asyncio.to_thread(self._encode_query_sync, text)

    def _encode_query_sync(self, text: str) -> list[float]:
        # e5 convention: prefijo "query: " para queries
        model = self._ensure_model()
        vec = model.encode([f"query: {text}"], normalize_embeddings=True, convert_to_numpy=True)
        return vec[0].tolist()


def _resolve_environment() -> str:
    """Entorno efectivo (minúsculas). Se lee dinámicamente de ENVIRONMENT
    para que el guard sea testeable con monkeypatch y coherente con config.py."""
    return os.environ.get("ENVIRONMENT", "development").strip().lower()


def _guard_non_semantic(embedder: BaseEmbedder, *, which: str, fell_back: bool) -> None:
    """BUG-4: hace ruidoso —o fatal— resolver a un embedder NO-semántico.

    - En producción/staging: RuntimeError. Indexar o consultar con vectores
      falsos (hash) corrompe el índice en silencio; preferimos fallar fuerte.
    - En dev: WARNING claro. El mock sigue siendo válido a propósito, pero
      queda marcado — nadie debería creer que el retrieval es real.
    """
    env = _resolve_environment()
    reason = (
        "EMBEDDER sin setear y sentence-transformers no instalado "
        "(fallback silencioso a mock)"
        if fell_back
        else f"EMBEDDER={which!r}"
    )
    if env in _NON_DEV_ENVIRONMENTS:
        msg = (
            f"Embedder NO-semántico ({embedder.model_name}) en entorno '{env}': "
            f"{reason}. El RAG indexaría/consultaría con embeddings FALSOS (hash). "
            "Seteá EMBEDDER=gemini|local con las deps reales instaladas. "
            "Abortando para no corromper el índice."
        )
        logger.error(msg)
        raise RuntimeError(msg)
    logger.warning(
        "Embedder NO-semántico activo (%s) — %s. Válido en dev, pero el "
        "retrieval NO es real: vectores deterministas por hash, sin semántica. "
        "NUNCA usar así en producción.",
        embedder.model_name,
        reason,
    )


@lru_cache(maxsize=1)
def get_embedder() -> BaseEmbedder:
    """Factory: elige el embedder según config de entorno.

    Override con EMBEDDER=mock|local para tests.

    BUG-4: si se resuelve a un embedder NO-semántico (mock) —sea explícito por
    `EMBEDDER=mock` o por fallback silencioso cuando faltan las deps reales—
    `_guard_non_semantic` lo hace ruidoso en dev y fatal en producción, para
    que sea imposible indexar embeddings falsos creyendo que son reales.
    """
    which = os.environ.get("EMBEDDER", "").lower()
    fell_back = False

    if which == "mock":
        embedder: BaseEmbedder = MockEmbedder()
    elif which == "gemini":
        embedder = GeminiEmbedder()
    elif which == "local":
        embedder = SentenceTransformerEmbedder()
    else:
        # Default: intentar local, fallback a mock si falta sentence-transformers
        try:
            import sentence_transformers  # noqa: F401
            import torch  # noqa: F401

            embedder = SentenceTransformerEmbedder()
        except ImportError:
            embedder = MockEmbedder()
            fell_back = True

    if not embedder.is_semantic:
        _guard_non_semantic(embedder, which=which, fell_back=fell_back)

    return embedder
