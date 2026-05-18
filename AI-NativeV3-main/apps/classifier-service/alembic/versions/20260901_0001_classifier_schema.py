"""classifier_schema

Revision ID: 20260901_0001
Revises: 20260720_0001
Create Date: 2026-09-01

Agrega la tabla classifications a la base ctr_store.
Depende de la migración del ctr-service (que crea apply_tenant_rls).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classifications",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classifier_config_hash", sa.String(64), nullable=False),
        sa.Column("appropriation", sa.String(40), nullable=False),
        sa.Column("appropriation_reason", sa.Text, nullable=False),
        sa.Column("ct_summary", sa.Float, nullable=True),
        sa.Column("ccd_mean", sa.Float, nullable=True),
        sa.Column("ccd_orphan_ratio", sa.Float, nullable=True),
        sa.Column("cii_stability", sa.Float, nullable=True),
        sa.Column("cii_evolution", sa.Float, nullable=True),
        sa.Column("features", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name="pk_classifications"),
        sa.UniqueConstraint(
            "episode_id", "classifier_config_hash", name="uq_classifications_episode_config"
        ),
    )
    op.create_index("ix_classifications_tenant_id", "classifications", ["tenant_id"])
    op.create_index("ix_classifications_episode_id", "classifications", ["episode_id"])
    op.create_index("ix_classifications_comision_id", "classifications", ["comision_id"])
    op.create_index(
        "ix_classifications_episode_current", "classifications", ["episode_id", "is_current"]
    )
    op.execute("SELECT apply_tenant_rls('classifications')")


def downgrade() -> None:
    op.drop_table("classifications")
