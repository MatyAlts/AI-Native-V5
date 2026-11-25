"""HU-033: campus que arma el docente — bienvenida e introduccion de unidad

Revision ID: 20261124_0001
Revises: 20260830_0001
Create Date: 2026-11-24

Tres columnas nuevas, todas nullable (retrocompat: las unidades y comisiones
existentes quedan sin fecha, abiertas, y sin HTML):

- `comisiones.bienvenida_html` (Text): bienvenida del campus en HTML.
- `unidades.introduccion_html` (Text): introduccion de la unidad en HTML.
- `unidades.fecha_apertura` (Date): desde que dia se abre la unidad.

El HTML lo escribe el docente y puede traer JS; se guarda tal cual y se
muestra siempre dentro de `HtmlAislado` (iframe sandbox de `@platform/ui`).
Las dos tablas ya tienen RLS por tenant; columnas nuevas no requieren policy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261124_0001"
down_revision: str | None = "20260830_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comisiones", sa.Column("bienvenida_html", sa.Text(), nullable=True))
    op.add_column("unidades", sa.Column("introduccion_html", sa.Text(), nullable=True))
    op.add_column("unidades", sa.Column("fecha_apertura", sa.Date(), nullable=True))


def downgrade() -> None:
    """Borra las tres columnas y su contenido. Hacer dump antes en produccion."""
    op.drop_column("unidades", "fecha_apertura")
    op.drop_column("unidades", "introduccion_html")
    op.drop_column("comisiones", "bienvenida_html")
