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

IDEMPOTENTE A PROPOSITO (revision del PR #33, 2026-07-22). La descripcion de
arriba vale para una base limpia, pero NO para produccion: ahi la columna ya
existe porque alguien la agrego A MANO, salteandose Alembic. La evidencia es el
nombre de la constraint — `comisiones_invite_code_key`, el default de Postgres
para un UNIQUE sin nombrar, mientras que todo el resto de la tabla sigue el
NAMING_CONVENTION de `models/base.py:20-26` (`pk_comisiones`,
`uq_comision_codigo`, `ix_comisiones_tenant_id`, `fk_comisiones_materia_id_materias`).
Solo esa no. Con `alembic_version = 20260615_0003` en prod, esta es la proxima
migracion en correr y su primer `op.add_column` reventaba con DuplicateColumn.

No se uso `alembic stamp` porque resuelve prod y rompe todo lo demas: una base
limpia (CI, dev, tenant nuevo) SI necesita que la columna se cree. La misma
migracion tiene que servir en los dos mundos.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0001"
down_revision: str | None = "20260615_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(conn: sa.Connection) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'comisiones' AND column_name = 'invite_code'"
            )
        ).scalar()
    )


def _tiene_indice_unico(conn: sa.Connection) -> bool:
    """Cualquier indice unico sobre invite_code, sin importar su nombre.

    Cubre tanto el `uq_comisiones_invite_code` de esta migracion como el
    `comisiones_invite_code_key` que quedo a mano en produccion. Un UNIQUE
    constraint de Postgres esta respaldado por un indice, asi que aparece en
    `pg_indexes` igual que un CREATE INDEX explicito.
    """
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE tablename = 'comisiones' "
                "AND indexdef ILIKE '%invite_code%' AND indexdef ILIKE '%UNIQUE%'"
            )
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()

    if not _tiene_columna(conn):
        op.add_column(
            "comisiones",
            sa.Column("invite_code", sa.String(length=10), nullable=True),
        )

    # Único pero permitiendo múltiples NULL (comisiones sin código generado aún).
    # El UNIQUE plano de prod es funcionalmente equivalente: Postgres trata los
    # NULL como distintos por default (NULLS DISTINCT), asi que dos comisiones
    # sin codigo no colisionan en ninguno de los dos casos.
    if not _tiene_indice_unico(conn):
        op.create_index(
            "uq_comisiones_invite_code",
            "comisiones",
            ["invite_code"],
            unique=True,
            postgresql_where=sa.text("invite_code IS NOT NULL"),
        )


def downgrade() -> None:
    """Revierte solo lo que esta migracion pudo haber creado.

    OJO en produccion: la columna se agrego a mano antes de esta migracion, asi
    que el `drop_column` de abajo tambien se lleva ese parche y los invite_code
    en uso. Es el significado correcto de volver a 20260615_0003, pero hacer
    dump antes.
    """
    conn = op.get_bind()

    indices = [
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'comisiones' "
                "AND indexname = 'uq_comisiones_invite_code'"
            )
        )
    ]
    for nombre in indices:
        op.drop_index(nombre, table_name="comisiones")

    if _tiene_columna(conn):
        op.drop_column("comisiones", "invite_code")
