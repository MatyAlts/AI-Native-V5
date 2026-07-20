"""unidades: partial unique indexes (excluyen soft-deleted)

Revision ID: 20260514_0003
Revises: 20260514_0002
Create Date: 2026-05-14

Bug fix: los UNIQUE constraints `uq_unidad_orden` y `uq_unidad_nombre` no
filtraban por `deleted_at IS NULL`, asi que una Unidad soft-deleted seguia
ocupando su slot `(tenant_id, comision_id, orden)` y `(tenant_id,
comision_id, nombre)` permanentemente. Sintoma: crear -> borrar -> intentar
crear otra con mismo orden/nombre devolvia 201 mentiroso (la transaccion
rolleaba al commit por ser el constraint DEFERRABLE INITIALLY DEFERRED).

Fix: drop de los constraints + create de partial unique indexes con
`WHERE deleted_at IS NULL`. Las filas soft-deleted dejan de bloquear los
slots y el endpoint puede crear unidades nuevas con el mismo orden/nombre
una vez que la version vieja fue borrada.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260514_0003"
down_revision: str | Sequence[str] | None = "20260514_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_unidad_orden", "unidades", type_="unique")
    op.drop_constraint("uq_unidad_nombre", "unidades", type_="unique")
    op.create_index(
        "uq_unidad_orden",
        "unidades",
        ["tenant_id", "comision_id", "orden"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )
    op.create_index(
        "uq_unidad_nombre",
        "unidades",
        ["tenant_id", "comision_id", "nombre"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_unidad_nombre", table_name="unidades")
    op.drop_index("uq_unidad_orden", table_name="unidades")
    op.create_unique_constraint(
        "uq_unidad_nombre", "unidades", ["tenant_id", "comision_id", "nombre"]
    )
    op.create_unique_constraint(
        "uq_unidad_orden",
        "unidades",
        ["tenant_id", "comision_id", "orden"],
        deferrable=True,
        initially="DEFERRED",
    )
