"""add_inicial_codigo_to_tareas_practicas

Revision ID: 20260421_0003
Revises: 20260421_0002
Create Date: 2026-04-21

Agrega la columna `inicial_codigo` (TEXT, NULL) a `tareas_practicas`
para que los docentes puedan proveer un template de código inicial
que el estudiante ve en el editor al abrir un episodio. NULL significa
"sin template" — el campo es semánticamente significativo, no hay
default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0003"
down_revision: str | None = "20260421_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tareas_practicas",
        sa.Column("inicial_codigo", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tareas_practicas", "inicial_codigo")
