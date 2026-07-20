"""enable_rls_on_classifier_tables

Revision ID: 20260902_0002
Revises: 20260901_0001
Create Date: 2026-09-02

Activa Row-Level Security sobre las tablas del classifier-service que
tienen `tenant_id`:
  - classifications

El aislamiento multi-tenant del classifier es crítico porque ese es el
servicio que produce las etiquetas N4 que se exportan a investigadores —
una falla de aislamiento acá contamina el dataset de un tenant con datos
de otro.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260902_0002"
down_revision: str | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES_WITH_TENANT = ("classifications",)


def upgrade() -> None:
    for table in TABLES_WITH_TENANT:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table}
            ON {table}
            FOR ALL
            USING (
                tenant_id::text = current_setting('app.current_tenant', true)
            )
            WITH CHECK (
                tenant_id::text = current_setting('app.current_tenant', true)
            )
        """)


def downgrade() -> None:
    for table in TABLES_WITH_TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
