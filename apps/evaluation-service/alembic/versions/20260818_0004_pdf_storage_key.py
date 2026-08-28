"""correcciones_ia.pdf_storage_key — donde quedo el PDF de devolucion

El PDF que devuelve Active-IA se baja al cerrar la correccion y se guarda en
storage propio. Se guarda la key, no el contenido: un PDF en una columna de
Postgres infla la tabla que el docente consulta en cada apertura del form.

**Key no adivinable y prefijo propio.** Lleva un token random ademas de los
ids: sin eso, alguien con el `correccion_id` puede construir la key, y si el
bucket queda mal configurado eso es un link directo a la devolucion de un
alumno. Y NUNCA el bucket de materiales — ahi hay objetos que se sirven a la
comision entera.

Revision ID: 20260818_0004
Revises: 20260818_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0004"
down_revision: str | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("correcciones_ia")}
    if "pdf_storage_key" not in cols:
        op.add_column(
            "correcciones_ia",
            sa.Column("pdf_storage_key", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("correcciones_ia")}
    if "pdf_storage_key" in cols:
        op.drop_column("correcciones_ia", "pdf_storage_key")
