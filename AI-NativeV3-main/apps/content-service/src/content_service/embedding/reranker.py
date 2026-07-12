"""Re-ranker cross-encoder.

Después de obtener top-20 con similitud vectorial, pasamos los pares
(query, chunk) por un cross-encoder que produce scores mucho más
precisos que la similitud coseno de los embeddings independientes.

Default: `BAAI/bge-reranker-base` (~500MB, funciona en CPU aceptablemente).
En tests: identity re-ranker que devuelve scores 1.0 para todos.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any


class BaseReranker(ABC):
    model_name: str

    @abstractmethod
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Scores (más alto = más relevante). No ordena; solo puntúa."""


class IdentityReranker(BaseReranker):
    """Re-ranker pass-through: devuelve 1.0 para todo. Útil en tests."""

    model_name = "identity"

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [1.0] * len(documents)


class CrossEncoderReranker(BaseReranker):
    """Re-ranker real con sentence-transformers CrossEncoder."""

    model_name = "BAAI/bge-reranker-base"

    def __init__(self) -> None:
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        # CrossEncoder.predict() es CPU-bound (P-10/A2.9): corre en un thread
        # para NO bloquear el event loop. El resultado (los scores) no cambia.
        return await asyncio.to_thread(self._predict_sync, query, documents)

    def _predict_sync(self, query: str, documents: list[str]) -> list[float]:
        import math

        model = self._ensure_model()
        pairs = [(query, d) for d in documents]
        scores = model.predict(pairs, show_progress_bar=False).tolist()
        # BGE devuelve logits; convertir a 0-1 via sigmoid
        return [1 / (1 + math.exp(-s)) for s in scores]


@lru_cache(maxsize=1)
def get_reranker() -> BaseReranker:
    which = os.environ.get("RERANKER", "").lower()
    if which == "identity":
        return IdentityReranker()
    try:
        import sentence_transformers  # noqa: F401

        return CrossEncoderReranker()
    except ImportError:
        return IdentityReranker()
