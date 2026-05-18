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
from content_service.extractors import detect_format
from content_service.models import Material
from content_service.models.base import utc_now
from content_service.schemas import MaterialListOut, MaterialOut
from content_service.services import IngestionPipeline
from content_service.services.storage import get_storage, make_storage_key

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
