"""HU-036: plantillas de campus por materia

Revision ID: 20261125_0001
Revises: 20261124_0001
Create Date: 2026-11-25

Tabla `plantillas_campus`: copia del campus de una comision (bienvenida,
unidades con introduccion y TPs vigentes) que otro docente de la misma
materia aplica a su comision. `contenido` es JSONB con `version="campus_v1"`
(ver `services/plantilla_campus_service.py`); no lleva fechas ni ids de la
comision de origen.

RLS: ENABLE + FORCE ROW LEVEL SECURITY y policy de tenant, mismo patron que
`unidades` (20260507_0002, ADR-001).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261125_0001"
down_revision: str | None = "20261124_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plantillas_campus",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "materia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("materias.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("contenido", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_plantillas_campus_tenant_id", "plantillas_campus", ["tenant_id"])
    op.create_index("ix_plantillas_campus_materia_id", "plantillas_campus", ["materia_id"])
    op.create_index("ix_plantillas_campus_deleted_at", "plantillas_campus", ["deleted_at"])

    op.execute("ALTER TABLE plantillas_campus ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE plantillas_campus FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY plantillas_campus_tenant_isolation ON plantillas_campus "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


def downgrade() -> None:
    """Borra la tabla y todas las plantillas guardadas. Hacer dump antes en produccion."""
    op.execute("DROP POLICY IF EXISTS plantillas_campus_tenant_isolation ON plantillas_campus")
    op.execute("ALTER TABLE plantillas_campus DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_plantillas_campus_deleted_at", table_name="plantillas_campus")
    op.drop_index("ix_plantillas_campus_materia_id", table_name="plantillas_campus")
    op.drop_index("ix_plantillas_campus_tenant_id", table_name="plantillas_campus")
    op.drop_table("plantillas_campus")
