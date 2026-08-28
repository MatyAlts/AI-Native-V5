"""Storage de materiales originales.

El cliente S3 vive en `platform_ops.storage` desde que el `evaluation-service`
necesito guardar PDF: duplicarlo habria dejado dos `S3Storage` divergiendo.
Lo que queda aca es lo que es de MATERIALES y de nadie mas — la convencion de
naming de las keys y el bucket.

Se reexportan `BaseStorage`, `MockStorage` y `S3Storage` porque los importan
`routes/materiales.py` y los tests; mover el modulo no tiene por que romperlos.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from platform_ops.storage import (
    BaseStorage,
    MockStorage,
    S3Storage,
    build_storage,
    storage_key_from_path,
)

__all__ = [
    "BaseStorage",
    "MockStorage",
    "S3Storage",
    "get_storage",
    "make_storage_key",
    "storage_key_from_path",
]


def make_storage_key(tenant_id: UUID, comision_id: UUID, material_id: UUID, filename: str) -> str:
    """Convención de naming de objetos en storage."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    return f"materials/{tenant_id}/{comision_id}/{material_id}/original.{ext}"


@lru_cache(maxsize=1)
def get_storage() -> BaseStorage:
    """El storage de materiales. `STORAGE=mock|s3`."""
    return build_storage("S3_BUCKET_MATERIALS", "materials")
