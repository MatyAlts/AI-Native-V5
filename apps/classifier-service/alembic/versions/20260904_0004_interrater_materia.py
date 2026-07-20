"""interrater_ratings: add materia_id (scope global de materia)

Revision ID: 20260904_0004
Revises: 20260903_0003
Create Date: 2026-06-23

ADITIVA: agrega `materia_id` (nullable) a `interrater_ratings` para poder agregar
el acuerdo inter-jueces a nivel MATERIA (cruzando comisiones), no solo por comisión.
Las filas viejas quedan con `materia_id` NULL (eran comisión-scoped). No toca
`classifications` ni la reproducibilidad bit-a-bit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0004"
down_revision: str | None = "20260903_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interrater_ratings",
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_interrater_materia", "interrater_ratings", ["materia_id"])


def downgrade() -> None:
    op.drop_index("ix_interrater_materia", table_name="interrater_ratings")
    op.drop_column("interrater_ratings", "materia_id")
