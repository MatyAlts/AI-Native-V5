"""add_interrater_ratings

Revision ID: 20260903_0003
Revises: 20260902_0002
Create Date: 2026-06-20

Tabla de etiquetas HUMANAS inter-jueces (validación κ del clasificador).
ADITIVA: solo crea una tabla nueva, no toca nada existente. RLS por tenant
(apply_tenant_rls, definido por el ctr-service). Una fila por (episodio,
codificador); unique constraint para upsert al re-etiquetar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0003"
down_revision: str | None = "20260902_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interrater_ratings",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rater_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False, server_default="ejes"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "rated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interrater_ratings"),
        sa.UniqueConstraint(
            "tenant_id", "episode_id", "rater_id", name="uq_interrater_episode_rater"
        ),
    )
    op.create_index("ix_interrater_ratings_tenant_id", "interrater_ratings", ["tenant_id"])
    op.create_index("ix_interrater_ratings_episode_id", "interrater_ratings", ["episode_id"])
    op.create_index("ix_interrater_comision", "interrater_ratings", ["comision_id"])
    op.create_index("ix_interrater_ratings_rater_id", "interrater_ratings", ["rater_id"])
    op.execute("SELECT apply_tenant_rls('interrater_ratings')")


def downgrade() -> None:
    op.drop_table("interrater_ratings")
