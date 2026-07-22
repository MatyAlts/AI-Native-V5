"""add_byok_keys + byok_keys_usage

Revision ID: 20260504_0002
Revises: 20260504_0001
Create Date: 2026-05-04

Sec 3+5 epic ai-native-completion-and-byok / ADR-038 + ADR-039: tablas
para BYOK (Bring-Your-Own-Key) con scope tenant/facultad/materia,
multi-provider simultaneo (Anthropic/Gemini/Mistral/OpenAI), encriptacion
at-rest AES-GCM (helper en `packages/platform-ops/src/platform_ops/crypto.py`),
budget per-key.

Tablas:
1. `byok_keys` - keys configuradas con metadata (scope, provider, fingerprint,
   budget, encrypted_value).
2. `byok_keys_usage` - agregado mensual de tokens y costo por key (PK
   compuesta `(key_id, yyyymm)`). Soft-cap aplicado en runtime por el
   ai-gateway leyendo esta tabla.

Constraints:
- UNIQUE `(tenant_id, scope_type, scope_id, provider)` WHERE `revoked_at IS NULL`
  permite multi-provider simultaneo por scope (ej. una facultad puede tener
  Anthropic Y Gemini activas) pero no dos keys del mismo provider para el
  mismo scope.
- CHECK `scope_type IN ('tenant', 'facultad', 'materia')` con `scope_id`
  nullable solo para `scope_type='tenant'` (facultad/materia requieren ID).
- RLS por `tenant_id` (mismo patron que el resto del academic_main).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260504_0002"
down_revision: str | None = "20260504_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. byok_keys
    op.create_table(
        "byok_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "scope_type",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "provider",
            sa.String(32),
            nullable=False,
        ),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=False),
        sa.Column(
            "fingerprint_last4",
            sa.String(4),
            nullable=False,
            comment="Ultimos 4 chars del plaintext de la key, para identificar sin exponer",
        ),
        sa.Column("monthly_budget_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft-revoke: la key queda en disco para audit pero NO resuelve",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant', 'facultad', 'materia')",
            name="ck_byok_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'tenant' AND scope_id IS NULL) OR "
            "(scope_type IN ('facultad', 'materia') AND scope_id IS NOT NULL)",
            name="ck_byok_scope_id_consistency",
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'gemini', 'mistral', 'openai')",
            name="ck_byok_provider",
        ),
    )

    # UNIQUE parcial: una key activa por (tenant, scope, provider)
    op.create_index(
        "uq_byok_keys_active",
        "byok_keys",
        ["tenant_id", "scope_type", "scope_id", "provider"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # RLS: misma policy que el resto de tablas con tenant_id
    op.execute("ALTER TABLE byok_keys ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY byok_keys_tenant_isolation ON byok_keys "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )

    # 2. byok_keys_usage
    op.create_table(
        "byok_keys_usage",
        sa.Column(
            "key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("byok_keys.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "yyyymm",
            sa.String(6),
            primary_key=True,
            comment="Mes en formato YYYYMM, ej. '202605'",
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tokens_input_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_output_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd_total", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("request_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "yyyymm ~ '^[0-9]{6}$'",
            name="ck_byok_usage_yyyymm",
        ),
    )

    op.execute("ALTER TABLE byok_keys_usage ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY byok_keys_usage_tenant_isolation ON byok_keys_usage "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS byok_keys_usage_tenant_isolation ON byok_keys_usage")
    op.drop_table("byok_keys_usage")

    op.execute("DROP POLICY IF EXISTS byok_keys_tenant_isolation ON byok_keys")
    op.drop_index("uq_byok_keys_active", table_name="byok_keys")
    op.drop_table("byok_keys")
