"""Endpoints de gestión de materiales."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.auth import (
    MATERIAL_UPLOAD_ROLES,
    User,
    get_db,
    require_role,
)
from content_service.embedding import get_embedder, get_reranker
from content_service.embedding.embedder import MockEmbedder
from content_service.extractors import detect_format
from content_service.models import Chunk, Material
from content_service.models.base import utc_now
from content_service.schemas import (
    ChunkOut,
    MaterialChunksOut,
    MaterialListOut,
    MaterialOut,
    RetrievalRequest,
    RetrievalTestRequest,
    RetrievalTestResponse,
)
from content_service.services import IngestionPipeline, RetrievalService
from content_service.services.storage import (
    get_storage,
    make_storage_key,
    storage_key_from_path,
)


def _is_semantic_model(model_name: str | None) -> bool | None:
    """True si el `embedding_model` persistido corresponde a un embedder real.

    None cuando no hay chunks (no se puede afirmar nada). El mock queda
    identificado por su `model_name` de clase (BUG-4 / F3(d))."""
    if model_name is None:
        return None
    return model_name != MockEmbedder.model_name

router = APIRouter(prefix="/api/v1/materiales", tags=["materiales"])


@router.post(
    "",
    response_model=MaterialOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_material(
    materia_id: UUID = Form(...),
    file: UploadFile = File(...),
    comision_id: UUID | None = Form(default=None),
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MaterialOut:
    """Sube un material a una materia y lo ingesta en el RAG.

    La ingesta (extracción + chunking + embedding) es síncrona en F2 y
    puede tardar segundos. En F3 se mueve a job async con progress polling.

    `materia_id` es el scope principal. `comision_id` es opcional (deprecated)
    y se guarda solo para backwards-compat.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename faltante",
        )

    # Tamaño máximo: 50 MB por F2. Videos grandes llegan en F3 con upload resumable.
    MAX_BYTES = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo excede {MAX_BYTES // (1024 * 1024)} MB",
        )

    # Detectar formato antes de persistir
    fmt = detect_format(file.filename, content)
    if fmt == "unknown":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no soportado para '{file.filename}'. Tipos válidos: PDF, Markdown, ZIP de código, texto plano.",
        )

    # Crear registro en DB
    material_id = uuid4()
    # storage_key sigue usando comision_id en el path para no reescribir objetos existentes
    storage_scope_id = comision_id or materia_id
    storage_key = make_storage_key(user.tenant_id, storage_scope_id, material_id, file.filename)

    # Subir a storage
    storage = get_storage()
    storage_path = await storage.put(
        storage_key,
        content,
        content_type=file.content_type or "application/octet-stream",
    )

    # Persistir Material en estado "uploaded"
    material = Material(
        id=material_id,
        tenant_id=user.tenant_id,
        materia_id=materia_id,
        comision_id=comision_id,
        tipo=fmt,
        nombre=file.filename,
        tamano_bytes=len(content),
        storage_path=storage_path,
        estado="uploaded",
        uploaded_by=user.id,
        meta={"content_type": file.content_type},
    )
    db.add(material)
    await db.flush()

    # Ingestar en el mismo request (F2) — flush intermedio en cada cambio de estado
    pipeline = IngestionPipeline(db)
    await pipeline.ingest(material, content, file.filename)

    refreshed = await db.get(Material, material_id)
    return MaterialOut.model_validate(refreshed or material)


@router.get("", response_model=MaterialListOut)
async def list_materiales(
    materia_id: UUID | None = Query(default=None),
    comision_id: UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    cursor: UUID | None = None,
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MaterialListOut:
    """Lista materiales. Filtra por `materia_id` (preferido) o `comision_id` (deprecated)."""
    stmt = select(Material).where(Material.deleted_at.is_(None))
    if materia_id:
        stmt = stmt.where(Material.materia_id == materia_id)
    elif comision_id:
        stmt = stmt.where(Material.comision_id == comision_id)
    if cursor:
        stmt = stmt.where(Material.id > cursor)
    stmt = stmt.order_by(Material.id).limit(limit)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return MaterialListOut(
        data=[MaterialOut.model_validate(m) for m in items],
        meta={
            "cursor_next": str(items[-1].id) if len(items) == limit else None,
        },
    )


@router.post("/probar-retrieval", response_model=RetrievalTestResponse)
async def probar_retrieval(
    request: RetrievalTestRequest,
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> RetrievalTestResponse:
    """Corre el retrieval RAG REAL (embed query + búsqueda vectorial + rerank)
    para que el docente verifique su corpus. Read-only: no muta nada.

    Devuelve los top-k chunks con su `score_vector` y `score_rerank`, más el
    modo del pipeline (`embedder_model` / `is_semantic_embedding` /
    `reranker_model`) — si `is_semantic_embedding=False` los scores son sobre
    vectores mock (hash) y NO reflejan relevancia real (BUG-4 / F3(d))."""
    svc = RetrievalService(db)
    result = await svc.retrieve(
        RetrievalRequest(
            query=request.query,
            materia_id=request.materia_id,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )
    )
    embedder = get_embedder()
    reranker = get_reranker()
    return RetrievalTestResponse(
        chunks=result.chunks,
        chunks_used_hash=result.chunks_used_hash,
        latency_ms=result.latency_ms,
        rerank_applied=reranker.model_name != "identity",
        embedder_model=embedder.model_name,
        is_semantic_embedding=embedder.is_semantic,
        reranker_model=reranker.model_name,
    )


@router.get("/{material_id}", response_model=MaterialOut)
async def get_material(
    material_id: UUID,
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MaterialOut:
    result = await db.execute(
        select(Material).where(
            Material.id == material_id,
            Material.deleted_at.is_(None),
        )
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material {material_id} no encontrado",
        )
    return MaterialOut.model_validate(material)


@router.get("/{material_id}/chunks", response_model=MaterialChunksOut)
async def list_material_chunks(
    material_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MaterialChunksOut:
    """Lista los chunks generados de un material (texto, orden, metadata).

    Read-only. Paginado por `position` (offset/limit). Expone el modo de
    embedding con el que se indexó para que el docente distinga un índice real
    de uno mock (F3 — observabilidad del RAG)."""
    material = await db.get(Material, material_id)
    if material is None or material.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material {material_id} no encontrado",
        )

    result = await db.execute(
        select(Chunk)
        .where(Chunk.material_id == material_id)
        .order_by(Chunk.position)
        .offset(offset)
        .limit(limit)
    )
    chunks = list(result.scalars().all())

    data = [
        ChunkOut(
            id=c.id,
            material_id=c.material_id,
            comision_id=c.comision_id,
            materia_id=c.materia_id,
            contenido=c.contenido,
            chunk_type=c.chunk_type,
            position=c.position,
            meta=c.meta or {},
            embedding_model=c.embedding_model,
            has_embedding=c.embedding is not None,
        )
        for c in chunks
    ]
    embedding_model = chunks[0].embedding_model if chunks else None
    return MaterialChunksOut(
        material_id=material.id,
        estado=material.estado,
        chunks_count=material.chunks_count,
        embedding_model=embedding_model,
        is_semantic_embedding=_is_semantic_model(embedding_model),
        data=data,
        meta={
            "offset": offset,
            "limit": limit,
            "returned": len(data),
            "next_offset": offset + len(data) if len(data) == limit else None,
        },
    )


@router.post("/{material_id}/reingest", response_model=MaterialOut)
async def reingest_material(
    material_id: UUID,
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> MaterialOut:
    """Re-procesa un material desde su archivo original en storage.

    Útil cuando un material quedó en `failed` o sin chunks (ej. embedder caído),
    o para re-indexar tras activar el embedder real. Re-descarga el original,
    borra los chunks viejos y re-corre extracción + chunking + embedding. La
    ingesta ya es idempotente por `material_id` (borra chunks previos)."""
    material = await db.get(Material, material_id)
    if material is None or material.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material {material_id} no encontrado",
        )

    storage = get_storage()
    key = storage_key_from_path(material.storage_path)
    try:
        content = await storage.get(key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El archivo original ya no está disponible en storage; no se puede reprocesar.",
        ) from exc

    pipeline = IngestionPipeline(db)
    await pipeline.ingest(material, content, material.nombre)

    refreshed = await db.get(Material, material_id)
    return MaterialOut.model_validate(refreshed or material)


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: UUID,
    user: User = Depends(require_role(*MATERIAL_UPLOAD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete: marca el material como borrado y sus chunks dejan de ser retornados.

    El contenido físico en storage se conserva (F5 decidirá política de GC).
    """
    result = await db.execute(select(Material).where(Material.id == material_id))
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material {material_id} no encontrado",
        )
    material.deleted_at = utc_now()
    await db.flush()
