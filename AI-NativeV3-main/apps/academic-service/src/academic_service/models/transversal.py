"""Tablas transversales: audit_log (auditoría) y casbin_rules (permisos)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from academic_service.models.base import (
    Base,
    TenantMixin,
    utc_now,
)


class AuditLog(Base, TenantMixin):
    """Registro append-only de toda operación de escritura relevante.

    Escrito en la misma transacción que la operación principal, de modo
    que si la operación rolbaquea el audit también. ADR no explícito
    (aceptado como estándar operacional).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # ej. "comision.create", "carrera.update"
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # estructura: {"before": {...}, "after": {...}} para diffs
    request_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )


class CasbinRule(Base):
    """Persistencia de policies Casbin (ADR-008).

    Las policies se modifican vía migraciones + adapter de Casbin.
    Los cambios en runtime son posibles pero excepcionales (ej. un
    docente_admin otorgando acceso puntual).
    """

    __tablename__ = "casbin_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ptype: Mapped[str] = mapped_column(String(10), nullable=False)  # p, g, g2...
    v0: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    v1: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    v2: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    v3: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v4: Mapped[str | None] = mapped_column(String(256), nullable=True)
    v5: Mapped[str | None] = mapped_column(String(256), nullable=True)

    def __str__(self) -> str:
        arr = [self.ptype]
        for v in (self.v0, self.v1, self.v2, self.v3, self.v4, self.v5):
            if v is None:
                break
            arr.append(v)
        return ", ".join(arr)
