"""Modelos del content-service."""

from content_service.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    utc_now,
)
from content_service.models.material import EMBEDDING_DIM, Chunk, Material

__all__ = [
    "EMBEDDING_DIM",
    "Base",
    "Chunk",
    "Material",
    "TenantMixin",
    "TimestampMixin",
    "utc_now",
]
