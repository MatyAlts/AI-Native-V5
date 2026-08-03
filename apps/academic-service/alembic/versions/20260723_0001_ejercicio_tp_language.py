"""ejercicio.language y tarea_practica.language — soporte multi-lenguaje

Revision ID: 20260723_0001
Revises: 20260721_0001
Create Date: 2026-07-23

Primer paso del soporte de Java (epic `java-language-model`). Agrega el lenguaje
de programacion como atributo de primera clase del banco de ejercicios y de las
TPs.

`server_default='python'` completa las filas existentes en el mismo ALTER TABLE:
el banco del piloto es integramente Python (169 ejercicios, 31 TPs), asi que el
default es semanticamente correcto y no un marcador de posicion. Evita el patron
de tres pasos (nullable -> UPDATE -> SET NOT NULL).

SIN CheckConstraint a proposito. El conjunto de lenguajes admitidos vive en
`platform_contracts.academic.Language`, que es el gate real de la API. Cerrarlo
en la base obligaria a una migracion por cada lenguaje futuro — mismo criterio
que llevo a 20260611_0001 a sacarle el CHECK a `unidad_tematica`.

Sin cambios de RLS: ambas tablas ya tienen policy activa y forzada; esto es un
ADD COLUMN sobre tabla existente, no una tabla nueva. Mismo patron que
20260615_0002 (tarea_practica.permite_pausa).

IDEMPOTENTE. No porque se espere que las columnas existan, sino porque en este
repo ya aparecio una columna agregada a mano en produccion salteandose Alembic
(`comisiones.invite_code`, detectada al revisar el PR #33 el 2026-07-22), y no
esta relevado cuanta deriva mas hay entre el schema del repo y el de prod.
Verificar antes de agregar cuesta dos SELECT y evita un DuplicateColumn que,
por el `|| echo` del entrypoint de este servicio, se tragaria en silencio
dejando el deploy en verde y la migracion sin aplicar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0001"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = ("ejercicios", "tareas_practicas")


def _tiene_columna(conn: sa.Connection, tabla: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :tabla AND column_name = 'language'"
            ),
            {"tabla": tabla},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    for tabla in _TABLAS:
        if not _tiene_columna(conn, tabla):
            op.add_column(
                tabla,
                sa.Column(
                    "language",
                    sa.String(length=20),
                    nullable=False,
                    server_default="python",
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()
    for tabla in _TABLAS:
        if _tiene_columna(conn, tabla):
            op.drop_column(tabla, "language")
