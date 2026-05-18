"""force_rls_byok_entregas_calificaciones

Revision ID: 20260507_0001
Revises: 20260506_0001
Create Date: 2026-05-07

Las tablas byok_keys, byok_keys_usage, entregas y calificaciones ya
tienen ENABLE ROW LEVEL SECURITY + policy tenant_isolation, pero les
falta FORCE ROW LEVEL SECURITY. Sin FORCE, el owner de la tabla
bypasea RLS silenciosamente — lo que rompe el invariante de
aislamiento multi-tenant (ADR-001). Detectado por make check-rls.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260507_0001"
down_revision: str | None = "20260506_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("byok_keys", "byok_keys_usage", "entregas", "calificaciones")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"
        )
