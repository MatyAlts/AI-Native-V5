"""comision.invite_code — código de auto-inscripción por comisión

Revision ID: 20260721_0001
Revises: 20260615_0003
Create Date: 2026-07-21

El modelo `Comision.invite_code` (operacional.py:78) se agregó para
auto-inscripción por código pero nunca tuvo su migración, dejando la columna
inexistente en la DB y rompiendo con `UndefinedColumnError` todo
`GET/POST /api/v1/comisiones` y `/comisiones/mis` (usado en el bootstrap de
sesión de los 3 frontends) — devuelve 500. Es el bug NB-1: lo detecta el smoke
`test_api_gateway_routes_to_academic_via_proxy` (GET /comisiones vía gateway
daba 500). Esta migración cierra ese gap. Columna `String(10)`,
`nullable=True` (retrocompat: las comisiones existentes quedan sin código hasta
que el docente genere uno) y única vía índice parcial que ignora NULLs — dos
comisiones sin código no colisionan. Tabla ya con RLS por tenant; no requiere
policy nueva.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0001"
down_revision: str | None = "20260615_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comisiones",
        sa.Column("invite_code", sa.String(length=10), nullable=True),
    )
    # Único pero permitiendo múltiples NULL (comisiones sin código generado aún).
    op.create_index(
        "uq_comisiones_invite_code",
        "comisiones",
        ["invite_code"],
        unique=True,
        postgresql_where=sa.text("invite_code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_comisiones_invite_code", table_name="comisiones")
    op.drop_column("comisiones", "invite_code")
