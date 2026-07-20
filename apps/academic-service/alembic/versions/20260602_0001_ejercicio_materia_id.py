"""ejercicio.materia_id — banco de ejercicios scopeado por materia (Prog 1, Prog 2, …)

Revision ID: 20260602_0001
Revises: 20260601_0001
Create Date: 2026-06-02

El banco de ejercicios era global por tenant (filtrable solo por unidad_tematica
/dificultad). Se agrega `materia_id` (nullable, FK a materias) para poder
filtrar el banco por materia: cada docente ve los ejercicios de la materia de
su comisión activa. Nullable para no romper el banco histórico (ejercicios sin
materia siguen existiendo; quedan fuera del filtro por materia hasta que se les
asigne una). Index para el filtro de listado.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260602_0001"
down_revision: str | None = "20260601_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ejercicios",
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ejercicios_materia_id",
        "ejercicios",
        "materias",
        ["materia_id"],
        ["id"],
    )
    op.create_index(
        "ix_ejercicios_materia_id",
        "ejercicios",
        ["materia_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ejercicios_materia_id", table_name="ejercicios")
    op.drop_constraint("fk_ejercicios_materia_id", "ejercicios", type_="foreignkey")
    op.drop_column("ejercicios", "materia_id")
