"""clasificaciones_pendientes

Revision ID: 20261126_0009
Revises: 20261126_0008
Create Date: 2026-11-26

HU-051: barrido de episodios pendientes de clasificar. Desde la HU-050 el
`POST /classify_episode/{id}` responde 202 cuando el CTR todavía no guardó el
`episodio_cerrado`, y la web del alumno reintenta ~54 s. Si la cola del CTR
tarda más (en prod hubo un atraso de 2 h 30 min), nadie vuelve a pedir la
clasificación. Con esta tabla el clasificador se anota cada 202 y el barrido
(`services/barrido.py`) lo reintenta solo.

ADITIVA: una tabla nueva, no toca filas ni columnas existentes. RLS por tenant
vía `apply_tenant_rls` (mismo mecanismo que `classification_reviews` y las
tablas del estudio, ADR-001).

- Una sola fila por `(tenant_id, episode_id)`: repetir el 202 no duplica
  (`INSERT ... ON CONFLICT DO NOTHING`).
- `estado`: 'pendiente' | 'clasificado' | 'descartado'. Nada se borra: un
  pendiente que pasó `barrido_pendiente_max_dias` sin cierre queda
  'descartado' como registro.
- `creado_at` es la primera anotación (de ahí se cuenta el vencimiento);
  `actualizado_at` e `intentos` son para operar (cuántas veces se le preguntó
  al CTR y cuándo fue la última).
- Índice parcial sobre los 'pendiente': es lo único que el barrido lee en
  cada pasada, y su tamaño es proporcional a lo que falta clasificar, no a la
  historia.

Downgrade: borra la tabla. Lo que pierde es la lista de pendientes; ninguna
clasificación vive acá.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261126_0009"
down_revision: str | None = "20261126_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "clasificaciones_pendientes"


def upgrade() -> None:
    op.create_table(
        TABLA,
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("intentos", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "creado_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clasificaciones_pendientes"),
        sa.UniqueConstraint(
            "tenant_id", "episode_id", name="uq_clasificaciones_pendientes_tenant_episode"
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'clasificado', 'descartado')",
            # La naming convention del modelo lo deja ck_clasificaciones_pendientes_estado.
            name="estado",
        ),
    )
    op.create_index("ix_clasificaciones_pendientes_tenant_id", TABLA, ["tenant_id"])
    op.execute(
        f"CREATE INDEX ix_clasificaciones_pendientes_abiertos ON {TABLA} "
        "(tenant_id, creado_at) WHERE estado = 'pendiente'"
    )
    op.execute(f"SELECT apply_tenant_rls('{TABLA}')")


def downgrade() -> None:
    op.drop_table(TABLA)
