"""ejercicio.unidad_tematica — agregar 'funciones' al CHECK constraint

Revision ID: 20260604_0001
Revises: 20260602_0001
Create Date: 2026-06-04

El banco de ejercicios restringia `unidad_tematica` a estructuras de control
('secuenciales', 'condicionales', 'repetitivas', 'mixtos'). Se agrega
'funciones' para soportar el Practico 6 (Funciones en Python) y futuros
ejercicios de la unidad Funciones. Solo amplia el conjunto permitido: no
modifica filas existentes ni rompe datos previos.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260604_0001"
down_revision: str | None = "20260602_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_ejercicios_unidad_tematica"
_TABLE = "ejercicios"
_NEW = (
    "unidad_tematica IN "
    "('secuenciales', 'condicionales', 'repetitivas', 'mixtos', 'funciones')"
)
_OLD = (
    "unidad_tematica IN "
    "('secuenciales', 'condicionales', 'repetitivas', 'mixtos')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _NEW)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _OLD)
