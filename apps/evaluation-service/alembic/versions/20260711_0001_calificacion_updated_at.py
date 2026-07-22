"""calificacion_updated_at

Revision ID: 20260711_0001
Revises: 20260510_0001
Create Date: 2026-07-11

NB-4 (re-calificar): agrega la columna ``updated_at`` a ``calificaciones`` para
registrar el momento de la ultima re-calificacion in-place. ``graded_at`` sigue
apuntando a la primera calificacion; ``updated_at`` marca la correccion mas
reciente (NULL mientras la nota no fue corregida).

Extension owned por evaluation-service (tracking en
``alembic_version_evaluation``). La tabla ``calificaciones`` vive en
``academic_main`` pero su schema se extiende desde evaluation — la migration
``20260506_0001`` de academic-service esta congelada (ver CLAUDE.md,
"Ownership cruzado entregas/calificaciones").

Defensiva/idempotente: solo agrega la columna si no existe (el ambiente piloto
puede correr esta migration sobre una tabla ya creada por academic-service).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0001"
down_revision: str | None = "20260510_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("calificaciones")}
    if "updated_at" not in cols:
        op.add_column(
            "calificaciones",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("calificaciones")}
    if "updated_at" in cols:
        op.drop_column("calificaciones", "updated_at")
