"""comision_nombre

Revision ID: 20260430_0001
Revises: 20260423_0001
Create Date: 2026-04-30

Agrega la columna `nombre VARCHAR(100) NOT NULL` a `comisiones` como
etiqueta humana del selector (ej. "A-Manana", "B-Tarde", "C-Noche") en
los frontends. La unicidad sigue siendo `(tenant_id, materia_id,
periodo_id, codigo)`; `nombre` NO entra al UNIQUE constraint.

Patron backfill-safe en una sola migracion:
1. add_column nullable=True
2. UPDATE comisiones SET nombre = codigo WHERE nombre IS NULL
3. alter_column nullable=False

Las filas pre-existentes quedan con `nombre = codigo` (semantica chata
pero correcta). El re-seed del piloto (`seed-3-comisiones.py`) sobreescribe
con valores legibles. Ver capability `academic-comisiones`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260430_0001"
down_revision: str | None = "20260423_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comisiones",
        sa.Column("nombre", sa.String(100), nullable=True),
    )
    op.execute("UPDATE comisiones SET nombre = codigo WHERE nombre IS NULL")
    op.alter_column("comisiones", "nombre", nullable=False)


def downgrade() -> None:
    op.drop_column("comisiones", "nombre")
