"""Tests de los endpoints de observabilidad del RAG (F3).

Cubren:
  - GET  /api/v1/materiales/{id}/chunks   → ver chunks generados + modo embedding
  - POST /api/v1/materiales/probar-retrieval → retrieval real read-only con scores
  - POST /api/v1/materiales/{id}/reingest → re-procesar un material

Mock-based (dependency_overrides sobre get_current_user + get_db + get_storage),
en línea con el patrón de academic-service/tests/integration. La RLS por tenant
queda cubierta por los tests que corren contra Postgres real.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from content_service.auth import get_current_user, get_db
from content_service.auth.dependencies import User
from content_service.embedding.embedder import get_embedder
from content_service.embedding.reranker import get_reranker
from content_service.main import app
from content_service.models import Chunk, Material
from content_service.schemas import RetrievalResponse
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _mock_embedder_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Fuerza el embedder/reranker mock deterministas y limpia sus caches."""
    monkeypatch.setenv("EMBEDDER", "mock")
    monkeypatch.setenv("RERANKER", "identity")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    get_embedder.cache_clear()
    get_reranker.cache_clear()
    yield
    get_embedder.cache_clear()
    get_reranker.cache_clear()


TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
MATERIA_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
# Dueño canónico de los materiales del setup (uploaded_by). El docente que loguea
# el fixture es el DUEÑO por default; los tests de "ajeno" usan otro id.
DOCENTE_ID = UUID("11111111-1111-1111-1111-111111111111")
OTRO_DOCENTE_ID = UUID("22222222-2222-2222-2222-222222222222")


def _docente(user_id: UUID = DOCENTE_ID) -> User:
    return User(
        id=user_id,
        tenant_id=TENANT_ID,
        email="docente@demo.edu",
        roles=frozenset({"docente"}),
        realm=str(TENANT_ID),
    )


def _superadmin() -> User:
    return User(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email="admin@demo.edu",
        roles=frozenset({"superadmin"}),
        realm=str(TENANT_ID),
    )


def _material(
    material_id: UUID,
    *,
    estado: str = "indexed",
    chunks_count: int = 2,
    uploaded_by: UUID = DOCENTE_ID,
) -> Material:
    return Material(
        id=material_id,
        tenant_id=TENANT_ID,
        materia_id=MATERIA_ID,
        comision_id=None,
        tipo="markdown",
        nombre="guia.md",
        tamano_bytes=10,
        storage_path="mock://materials/t/m/x/original.md",
        estado=estado,
        uploaded_by=uploaded_by,
        chunks_count=chunks_count,
        meta={},
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
    )


def _chunk(material_id: UUID, position: int, *, model: str | None, with_vec: bool) -> Chunk:
    return Chunk(
        id=uuid4(),
        tenant_id=TENANT_ID,
        material_id=material_id,
        materia_id=MATERIA_ID,
        comision_id=None,
        contenido=f"chunk {position}",
        contenido_hash="h" * 64,
        embedding=[0.1] * 1024 if with_vec else None,
        embedding_model=model,
        position=position,
        chunk_type="prose",
        meta={"source_page": position},
    )


@pytest.fixture
def client_with(monkeypatch: pytest.MonkeyPatch):
    """Cliente con user=docente y un session mock configurable.

    Devuelve (client, ctx) donde ctx permite setear:
      - ctx["material"]: objeto devuelto por db.get(Material, id)
      - ctx["chunks"]: lista devuelta por scalars().all()
      - ctx["retrieve"]: RetrievalResponse a devolver por RetrievalService
      - ctx["user"]: User que loguea (default docente dueño DOCENTE_ID)
      - ctx["owns_materia"]: fila devuelta por result.first() en el gate de
        propiedad por materia (probar-retrieval). Truthy = tiene material propio.
    """
    ctx: dict[str, Any] = {
        "material": None,
        "chunks": [],
        "retrieve": None,
        "user": _docente(),
        "owns_materia": (DOCENTE_ID,),
    }

    async def _override_user() -> User:
        return ctx["user"]

    async def _override_db():
        session = MagicMock()

        async def _get(model, ident):
            return ctx["material"]

        scalars = MagicMock()
        scalars.all = MagicMock(return_value=ctx["chunks"])
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        # first() alimenta el gate assert_materia_upload_access (probar-retrieval)
        result.first = MagicMock(side_effect=lambda: ctx["owns_materia"])

        session.get = AsyncMock(side_effect=_get)
        session.execute = AsyncMock(return_value=result)
        session.flush = AsyncMock()
        yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), ctx
    finally:
        app.dependency_overrides.clear()


# ── GET /{id}/chunks ─────────────────────────────────────────────────


def test_list_chunks_returns_chunks_and_mock_embedding_flag(client_with) -> None:
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid)
    ctx["chunks"] = [
        _chunk(mid, 0, model="mock-deterministic", with_vec=True),
        _chunk(mid, 1, model="mock-deterministic", with_vec=True),
    ]

    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 200
    body = r.json()
    assert body["material_id"] == str(mid)
    assert body["chunks_count"] == 2
    assert body["embedding_model"] == "mock-deterministic"
    # El mock NO es semántico → la UI puede avisar que el retrieval no es real.
    assert body["is_semantic_embedding"] is False
    assert len(body["data"]) == 2
    assert body["data"][0]["position"] == 0
    assert body["data"][0]["has_embedding"] is True
    assert body["data"][0]["contenido"] == "chunk 0"
    assert body["data"][0]["meta"]["source_page"] == 0


def test_list_chunks_real_embedder_marks_semantic(client_with) -> None:
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid)
    ctx["chunks"] = [_chunk(mid, 0, model="gemini-embedding-001", with_vec=True)]

    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 200
    body = r.json()
    assert body["embedding_model"] == "gemini-embedding-001"
    assert body["is_semantic_embedding"] is True


def test_list_chunks_material_not_found(client_with) -> None:
    client, ctx = client_with
    ctx["material"] = None
    r = client.get(f"/api/v1/materiales/{uuid4()}/chunks")
    assert r.status_code == 404


def test_list_chunks_no_chunks_yet(client_with) -> None:
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid, estado="failed", chunks_count=0)
    ctx["chunks"] = []
    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["is_semantic_embedding"] is None
    assert body["estado"] == "failed"


# ── POST /probar-retrieval ───────────────────────────────────────────


def test_probar_retrieval_exposes_scores_and_mock_mode(
    client_with, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ctx = client_with

    chunk_id = uuid4()
    fake = RetrievalResponse(
        chunks=[
            {
                "id": chunk_id,
                "contenido": "La recursion es cuando una funcion se llama a si misma.",
                "material_id": uuid4(),
                "material_nombre": "guia.md",
                "position": 3,
                "chunk_type": "prose",
                "meta": {},
                "score_vector": 0.82,
                "score_rerank": 0.91,
            }
        ],
        chunks_used_hash="deadbeef",
        latency_ms=12.3,
        rerank_applied=False,
    )

    async def _fake_retrieve(self, request):
        return fake

    monkeypatch.setattr(
        "content_service.routes.materiales.RetrievalService.retrieve",
        _fake_retrieve,
    )

    r = client.post(
        "/api/v1/materiales/probar-retrieval",
        json={"query": "que es la recursion", "materia_id": str(MATERIA_ID), "top_k": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["score_vector"] == 0.82
    assert body["chunks"][0]["score_rerank"] == 0.91
    assert body["chunks_used_hash"] == "deadbeef"
    # Modo del pipeline expuesto: mock + identity ⇒ scores NO reales.
    assert body["embedder_model"] == "mock-deterministic"
    assert body["is_semantic_embedding"] is False
    assert body["reranker_model"] == "identity"
    assert body["rerank_applied"] is False


def test_probar_retrieval_requires_query(client_with) -> None:
    client, _ = client_with
    r = client.post(
        "/api/v1/materiales/probar-retrieval",
        json={"query": "", "materia_id": str(MATERIA_ID)},
    )
    assert r.status_code == 422


# ── POST /{id}/reingest ──────────────────────────────────────────────


def test_reingest_reprocesses_from_storage(
    client_with, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid, estado="failed", chunks_count=0)

    stored = MagicMock()
    stored.get = AsyncMock(return_value=b"# Recursion\n\nUn concepto fundamental.\n")
    monkeypatch.setattr(
        "content_service.routes.materiales.get_storage", lambda: stored
    )

    ingested: dict[str, Any] = {}

    async def _fake_ingest(self, material, content, filename):
        ingested["content"] = content
        ingested["filename"] = filename
        material.estado = "indexed"
        material.chunks_count = 1
        return MagicMock()

    monkeypatch.setattr(
        "content_service.routes.materiales.IngestionPipeline.ingest",
        _fake_ingest,
    )

    r = client.post(f"/api/v1/materiales/{mid}/reingest")
    assert r.status_code == 200
    stored.get.assert_awaited_once()
    assert ingested["filename"] == "guia.md"
    assert ingested["content"].startswith(b"# Recursion")


def test_reingest_material_not_found(client_with) -> None:
    client, ctx = client_with
    ctx["material"] = None
    r = client.post(f"/api/v1/materiales/{uuid4()}/reingest")
    assert r.status_code == 404


def test_reingest_missing_original_is_conflict(
    client_with, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid)

    stored = MagicMock()
    stored.get = AsyncMock(side_effect=FileNotFoundError("gone"))
    monkeypatch.setattr(
        "content_service.routes.materiales.get_storage", lambda: stored
    )

    r = client.post(f"/api/v1/materiales/{mid}/reingest")
    assert r.status_code == 409


# ── FIX C: propiedad/acceso por material ─────────────────────────────


def test_list_chunks_ajeno_es_not_found(client_with) -> None:
    """Docente que NO subió el material no ve sus chunks (fail-closed, 404)."""
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid, uploaded_by=OTRO_DOCENTE_ID)
    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 404


def test_list_chunks_owner_ok(client_with) -> None:
    """El dueño del material SÍ ve sus chunks."""
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid, uploaded_by=DOCENTE_ID)
    ctx["chunks"] = [_chunk(mid, 0, model="mock-deterministic", with_vec=True)]
    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 200


def test_list_chunks_superadmin_ve_ajeno(client_with) -> None:
    """Superadmin (oversight) ve chunks de cualquier material del tenant."""
    client, ctx = client_with
    ctx["user"] = _superadmin()
    mid = uuid4()
    ctx["material"] = _material(mid, uploaded_by=OTRO_DOCENTE_ID)
    ctx["chunks"] = [_chunk(mid, 0, model="mock-deterministic", with_vec=True)]
    r = client.get(f"/api/v1/materiales/{mid}/chunks")
    assert r.status_code == 200


def test_reingest_ajeno_es_not_found(client_with, monkeypatch: pytest.MonkeyPatch) -> None:
    """El reingest DESTRUCTIVO sobre material ajeno se corta fail-closed (404)
    antes de tocar storage o el pipeline."""
    client, ctx = client_with
    mid = uuid4()
    ctx["material"] = _material(mid, uploaded_by=OTRO_DOCENTE_ID)

    stored = MagicMock()
    stored.get = AsyncMock(return_value=b"# x")
    monkeypatch.setattr("content_service.routes.materiales.get_storage", lambda: stored)

    ingest_called = {"v": False}

    async def _fake_ingest(self, material, content, filename):
        ingest_called["v"] = True
        return MagicMock()

    monkeypatch.setattr(
        "content_service.routes.materiales.IngestionPipeline.ingest", _fake_ingest
    )

    r = client.post(f"/api/v1/materiales/{mid}/reingest")
    assert r.status_code == 404
    # No se descargó el original ni se reprocesó nada.
    stored.get.assert_not_awaited()
    assert ingest_called["v"] is False


def test_reingest_superadmin_ve_ajeno(client_with, monkeypatch: pytest.MonkeyPatch) -> None:
    """Superadmin puede reingestar cualquier material del tenant."""
    client, ctx = client_with
    ctx["user"] = _superadmin()
    mid = uuid4()
    ctx["material"] = _material(mid, uploaded_by=OTRO_DOCENTE_ID)

    stored = MagicMock()
    stored.get = AsyncMock(return_value=b"# Recursion\n\nUn concepto.\n")
    monkeypatch.setattr("content_service.routes.materiales.get_storage", lambda: stored)

    async def _fake_ingest(self, material, content, filename):
        material.estado = "indexed"
        return MagicMock()

    monkeypatch.setattr(
        "content_service.routes.materiales.IngestionPipeline.ingest", _fake_ingest
    )

    r = client.post(f"/api/v1/materiales/{mid}/reingest")
    assert r.status_code == 200
    stored.get.assert_awaited_once()


def test_probar_retrieval_sin_material_propio_es_forbidden(
    client_with, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Docente sin material propio en la materia no puede correr retrieval (403)."""
    client, ctx = client_with
    ctx["owns_materia"] = None  # first() → sin fila → no subió material

    called = {"v": False}

    async def _fake_retrieve(self, request):
        called["v"] = True
        return MagicMock()

    monkeypatch.setattr(
        "content_service.routes.materiales.RetrievalService.retrieve", _fake_retrieve
    )

    r = client.post(
        "/api/v1/materiales/probar-retrieval",
        json={"query": "que es la recursion", "materia_id": str(MATERIA_ID)},
    )
    assert r.status_code == 403
    # Fail-closed: ni siquiera se corrió el retrieval.
    assert called["v"] is False


def test_probar_retrieval_superadmin_no_requiere_material_propio(
    client_with, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Superadmin corre retrieval sobre cualquier materia sin ser dueño."""
    client, ctx = client_with
    ctx["user"] = _superadmin()
    ctx["owns_materia"] = None  # no importa: oversight saltea el gate

    fake = RetrievalResponse(
        chunks=[], chunks_used_hash="x", latency_ms=1.0, rerank_applied=False
    )

    async def _fake_retrieve(self, request):
        return fake

    monkeypatch.setattr(
        "content_service.routes.materiales.RetrievalService.retrieve", _fake_retrieve
    )

    r = client.post(
        "/api/v1/materiales/probar-retrieval",
        json={"query": "que es la recursion", "materia_id": str(MATERIA_ID)},
    )
    assert r.status_code == 200


def test_storage_key_from_path_roundtrip() -> None:
    from content_service.services.storage import storage_key_from_path

    assert storage_key_from_path("mock://materials/t/c/m/original.md") == "materials/t/c/m/original.md"
    assert (
        storage_key_from_path("s3://materials/materials/t/c/m/original.pdf")
        == "materials/t/c/m/original.pdf"
    )
    assert storage_key_from_path("materials/plain/key.txt") == "materials/plain/key.txt"


# Silencia el lint de imports usados sólo por fixtures dinámicas.
_ = uuid
