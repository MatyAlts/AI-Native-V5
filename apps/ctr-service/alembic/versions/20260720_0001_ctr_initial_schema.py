"""ctr_initial_schema

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20

Crea las tablas del ctr-service en la base ctr_store con RLS activo.
Las tablas son append-only por diseño — no hay UPDATE/DELETE excepto en
`episodes` (que se actualiza con cada nuevo evento del stream).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── Episodes ──────────────────────────────────────────────────────
    op.create_table(
        "episodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_system_hash", sa.String(64), nullable=False),
        sa.Column("prompt_system_version", sa.String(30), nullable=False),
        sa.Column("classifier_config_hash", sa.String(64), nullable=False),
        sa.Column("curso_config_hash", sa.String(64), nullable=False),
        sa.Column("estado", sa.String(30), nullable=False, server_default="open"),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_chain_hash", sa.String(64), nullable=False, server_default="0" * 64),
        sa.Column("integrity_compromised", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id", name="pk_episodes"),
    )
    op.create_index("ix_episodes_tenant_id", "episodes", ["tenant_id"])
    op.create_index("ix_episodes_comision_id", "episodes", ["comision_id"])
    op.create_index("ix_episodes_student_pseudonym", "episodes", ["student_pseudonym"])
    op.create_index("ix_episodes_estado", "episodes", ["estado"])

    # ── Events ────────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("event_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("self_hash", sa.String(64), nullable=False),
        sa.Column("chain_hash", sa.String(64), nullable=False),
        sa.Column("prev_chain_hash", sa.String(64), nullable=False),
        sa.Column("prompt_system_hash", sa.String(64), nullable=False),
        sa.Column("prompt_system_version", sa.String(30), nullable=False),
        sa.Column("classifier_config_hash", sa.String(64), nullable=False),
        sa.Column(
            "persisted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["episodes.id"],
            name="fk_events_episode_id_episodes",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "event_uuid", name="uq_events_event_uuid"),
        sa.UniqueConstraint("tenant_id", "episode_id", "seq", name="uq_events_episode_seq"),
    )
    op.create_index("ix_events_tenant_id", "events", ["tenant_id"])
    op.create_index("ix_events_episode_id", "events", ["episode_id"])
    op.create_index("ix_events_episode_seq", "events", ["episode_id", "seq"])
    op.create_index("ix_events_chain_hash", "events", ["chain_hash"])

    # ── Dead letters ──────────────────────────────────────────────────
    op.create_table(
        "dead_letters",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=False),
        sa.Column("failed_attempts", sa.Integer, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "moved_to_dlq_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letters"),
    )
    op.create_index("ix_dead_letters_tenant_id", "dead_letters", ["tenant_id"])
    op.create_index("ix_dead_letters_episode_id", "dead_letters", ["episode_id"])

    # ── RLS ───────────────────────────────────────────────────────────
    for table in ("episodes", "events", "dead_letters"):
        op.execute(f"SELECT apply_tenant_rls('{table}')")


def downgrade() -> None:
    op.drop_table("dead_letters")
    op.drop_table("events")
    op.drop_table("episodes")
