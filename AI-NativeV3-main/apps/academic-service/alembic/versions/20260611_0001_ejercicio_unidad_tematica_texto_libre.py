"""ejercicio.unidad_tematica — quitar el CHECK (texto libre)

Revision ID: 20260611_0001
Revises: 20260604_0001
Create Date: 2026-06-11

La taxonomia de unidades NO es fija: cada materia define las suyas. Se elimina
el CHECK constraint que limitaba `unidad_tematica` a un conjunto cerrado, para
aceptar cualquier valor (texto libre). NO modifica filas existentes. El
downgrade recrea el CHECK con el conjunto de 5 unidades vigente al cambio.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260611_0001"
down_revision: str | None = "20260604_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_ejercicios_unidad_tematica"
_TABLE = "ejercicios"
_OLD = (
    "unidad_tematica IN "
    "('secuenciales', 'condicionales', 'repetitivas', 'mixtos', 'funciones')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")


def downgrade() -> None:
    op.create_check_constraint(_CONSTRAINT, _TABLE, _OLD)
