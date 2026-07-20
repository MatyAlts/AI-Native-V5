"""carrera_facultad_required

Revision ID: 20260422_0001
Revises: 20260421_0003
Create Date: 2026-04-22

Hace `carreras.facultad_id` NOT NULL — toda carrera del piloto pertenece a
una facultad. `universidad_id` queda como campo denormalizado derivado.

Verificado antes de la migración: no hay filas con `facultad_id IS NULL` en
`academic_main.carreras`, por lo que el `ALTER COLUMN ... SET NOT NULL` corre
sin backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260422_0001"
down_revision: str | None = "20260421_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("carreras", "facultad_id", nullable=False)


def downgrade() -> None:
    op.alter_column("carreras", "facultad_id", nullable=True)
