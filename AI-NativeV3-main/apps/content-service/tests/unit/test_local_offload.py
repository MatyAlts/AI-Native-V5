"""P-10 / A2.9: el embedder y el reranker locales son CPU-bound y NO deben
bloquear el event loop. Estos tests verifican que su cómputo síncrono
(`model.encode` / `model.predict`) se ejecuta en un thread distinto al del
event loop (via `asyncio.to_thread`), sin alterar el resultado.

No requieren sentence-transformers instalado: inyectan un modelo falso que
registra en qué thread corrió y devuelve un resultado determinista.
"""

from __future__ import annotations

import asyncio
import threading

from content_service.embedding.embedder import SentenceTransformerEmbedder
from content_service.embedding.reranker import CrossEncoderReranker


class _FakeArray(list):
    """Array-like mínimo con `.tolist()` (evita depender de numpy en tests)."""

    def tolist(self) -> list:
        return [x.tolist() if isinstance(x, _FakeArray) else x for x in self]


class _FakeSTModel:
    """Modelo falso estilo SentenceTransformer: registra el thread de `encode`."""

    def __init__(self) -> None:
        self.encode_thread: int | None = None

    def encode(self, texts, **_kwargs):
        self.encode_thread = threading.get_ident()
        # Vector determinista por texto (dim chico, irrelevante para el test).
        return _FakeArray(_FakeArray([float(len(t)), 1.0, 2.0]) for t in texts)


class _FakeCrossEncoder:
    """CrossEncoder falso: registra el thread de `predict`."""

    def __init__(self) -> None:
        self.predict_thread: int | None = None

    def predict(self, pairs, **_kwargs):
        self.predict_thread = threading.get_ident()
        # Logit 0.0 → sigmoid 0.5 para todos (resultado determinista).
        return _FakeArray(0.0 for _ in pairs)


async def test_embed_documents_corre_fuera_del_event_loop() -> None:
    embedder = SentenceTransformerEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake  # inyecta el modelo; _ensure_model lo devuelve tal cual

    loop_thread = threading.get_ident()
    result = await embedder.embed_documents(["hola", "mundo"])

    assert len(result) == 2
    # El cómputo corrió en OTRO thread (no bloqueó el event loop).
    assert fake.encode_thread is not None
    assert fake.encode_thread != loop_thread


async def test_embed_query_corre_fuera_del_event_loop() -> None:
    embedder = SentenceTransformerEmbedder()
    fake = _FakeSTModel()
    embedder._model = fake

    loop_thread = threading.get_ident()
    vec = await embedder.embed_query("qué es recursión?")

    assert isinstance(vec, list)
    assert fake.encode_thread is not None
    assert fake.encode_thread != loop_thread


async def test_embed_es_awaitable_no_bloqueante() -> None:
    """Mientras el embed CPU-bound corre en su thread, otra coroutine avanza."""
    embedder = SentenceTransformerEmbedder()

    barrier = threading.Event()

    class _BlockingModel(_FakeSTModel):
        def encode(self, texts, **kwargs):
            barrier.wait(timeout=5)  # bloquea el WORKER thread, no el loop
            return super().encode(texts, **kwargs)

    embedder._model = _BlockingModel()

    other_ran = False

    async def _other() -> None:
        nonlocal other_ran
        other_ran = True
        barrier.set()  # libera el worker thread una vez que el loop siguió girando

    _, _ = await asyncio.gather(embedder.embed_query("x"), _other())
    assert other_ran is True


async def test_rerank_corre_fuera_del_event_loop() -> None:
    reranker = CrossEncoderReranker()
    fake = _FakeCrossEncoder()
    reranker._model = fake

    loop_thread = threading.get_ident()
    scores = await reranker.rerank("query", ["doc a", "doc b", "doc c"])

    assert scores == [0.5, 0.5, 0.5]  # sigmoid(0) — resultado intacto
    assert fake.predict_thread is not None
    assert fake.predict_thread != loop_thread


async def test_rerank_lista_vacia_no_toca_el_modelo() -> None:
    reranker = CrossEncoderReranker()
    reranker._model = _FakeCrossEncoder()
    assert await reranker.rerank("query", []) == []
