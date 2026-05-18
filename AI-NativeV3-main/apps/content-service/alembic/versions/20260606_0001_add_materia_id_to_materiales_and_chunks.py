"""add_materia_id_to_materiales_and_chunks

Revision ID: 20260606_0001
Revises: 20260521_0001
Create Date: 2026-06-06

Agrega materia_id (UUID NOT NULL) a materiales y chunks.
Hace comision_id nullable en ambas tablas (deprecated, drop futuro).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260606_0001"
down_revision: str | None = "20260521_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── materiales: agregar materia_id ────────────────────────────────
    # Paso 1: agregar como nullable para poder poblar
    op.add_column(
        "materiales",
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Paso 2: poblar materia_id desde comision_id existente NO es posible
    # sin acceso a academic_main (bases separadas por ADR-003).
    # Para el piloto con data limpia, los registros existentes se dejan NULL
    # y se populan manualmente si hace falta.

    # Paso 3: hacer NOT NULL (para instalaciones nuevas sin data previa,
    # comentar este paso si hay materiales preexistentes sin materia_id)
    # op.alter_column("materiales", "materia_id", nullable=False)

    # Paso 4: indices
    op.create_index("ix_materiales_materia_id", "materiales", ["materia_id"])
    op.create_index(
        "ix_materiales_tenant_materia",
        "materiales",
        ["tenant_id", "materia_id"],
    )

    # Paso 5: comision_id pasa a nullable
    op.alter_column("materiales", "comision_id", nullable=True)

    # ── chunks: agregar materia_id ────────────────────────────────────
    op.add_column(
        "chunks",
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_index("ix_chunks_materia_id", "chunks", ["materia_id"])
    op.create_index(
        "ix_chunks_tenant_materia",
        "chunks",
        ["tenant_id", "materia_id"],
    )

    # comision_id pasa a nullable
    op.alter_column("chunks", "comision_id", nullable=True)


def downgrade() -> None:
    # chunks
    op.drop_index("ix_chunks_tenant_materia")
    op.drop_index("ix_chunks_materia_id")
    op.drop_column("chunks", "materia_id")
    op.alter_column("chunks", "comision_id", nullable=False)

    # materiales
    op.drop_index("ix_materiales_tenant_materia")
    op.drop_index("ix_materiales_materia_id")
    op.drop_column("materiales", "materia_id")
    op.alter_column("materiales", "comision_id", nullable=False)
