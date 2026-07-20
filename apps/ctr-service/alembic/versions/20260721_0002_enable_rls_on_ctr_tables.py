"""enable_rls_on_ctr_tables

Revision ID: 20260721_0002
Revises: 20260720_0001
Create Date: 2026-07-21

Activa Row-Level Security sobre las 3 tablas con `tenant_id` del ctr-service:
  - episodes
  - events
  - dead_letters (DLQ)

La política usa `current_setting('app.current_tenant')` como filtro, y
el adaptador real (packages/platform-ops/real_datasources.py) lo setea
al inicio de cada transacción con `SET LOCAL`.

**FORCE** ROW LEVEL SECURITY es crítico: incluso el owner de la tabla
respeta la política, evitando bypass accidental en migrations o consultas
ad-hoc con psql.

La cadena criptográfica del CTR se mantiene intacta — RLS solo filtra
qué filas son visibles, no modifica los hashes.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES_WITH_TENANT = ("episodes", "events", "dead_letters")


def upgrade() -> None:
    # 1. Crear rol de aplicación si no existe (usado por los servicios
    #    para conectarse; el rol bypasa RLS solo si se le da BYPASSRLS,
    #    que NO le damos acá — eso es decisión operacional del DBA).
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'platform_app') THEN
                CREATE ROLE platform_app NOLOGIN;
            END IF;
        END
        $$;
    """)

    # 2. Activar RLS + FORCE en cada tabla con tenant_id
    for table in TABLES_WITH_TENANT:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Policy: solo ver filas donde tenant_id = current_setting app.current_tenant
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

    # 3. Parámetro default vacío — sin SET LOCAL explícito, current_setting
    #    devuelve '' y no matchea ningún tenant_id real. Esto es el
    #    comportamiento fail-safe que queremos: olvidarse del SET LOCAL
    #    produce "no veo nada" en vez de "veo todo".
    op.execute("ALTER DATABASE ctr_store SET app.current_tenant = ''")


def downgrade() -> None:
    for table in TABLES_WITH_TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
