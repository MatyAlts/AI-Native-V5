"""Modelos SQLAlchemy del evaluation-service."""

from evaluation_service.models.base import Base, TenantMixin, TimestampMixin, fk_uuid, uuid_pk
from evaluation_service.models.entregas import Calificacion, Entrega

__all__ = [
    "Base",
    "Calificacion",
    "Entrega",
    "TenantMixin",
    "TimestampMixin",
    "fk_uuid",
    "uuid_pk",
]
