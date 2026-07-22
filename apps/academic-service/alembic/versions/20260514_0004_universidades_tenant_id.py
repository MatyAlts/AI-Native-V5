"""universidades: tenant_id + RLS forced (1 universidad = 1 tenant)

Revision ID: 20260514_0004
Revises: 20260514_0003
Create Date: 2026-05-14

Cierra el gap arquitectural: la tabla `universidades` era la unica de la
jerarquia academica SIN columna `tenant_id` y SIN RLS. Eso permitia que
una universidad nueva creada por el admin heredara el banco de ejercicios
del tenant en el que vivia el admin, rompiendo el aislamiento academico
entre universidades.

Cambios:
1. Agrega columna `tenant_id` (nullable inicialmente para backfill).
2. Backfill: por convencion, `tenant_id = id` (la universidad es su propio
   tenant). Esto matchea con la convencion que ya usaba el seed
   (UTN tenia universidad.id == tenant_id).
3. NOT NULL constraint.
4. Indice por `tenant_id`.
5. Habilita y fuerza RLS con policy `tenant_isolation`.

Despues de esta migration, crear una universidad nueva DEBE asignar
`tenant_id = id` (responsabilidad del service `universidad_service.create`).

BC-impact:
- Endpoint GET /universidades empieza a filtrar por tenant del caller.
- Antes, listaba TODAS las universidades. Ahora, solo las del tenant.
- Tests que asumian lista global de universidades pueden fallar y
  necesitan setear tenant explicito.

Downgrade:
- Drop policy, RLS, index, columna. Vuelve al modelo laxo previo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0004"
down_revision: str | Sequence[str] | None = "20260514_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Agregar columna nullable
    op.add_column(
        "universidades",
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2. Backfill: convencion tenant_id = id
    op.execute("UPDATE universidades SET tenant_id = id WHERE tenant_id IS NULL")

    # 3. NOT NULL
    op.alter_column("universidades", "tenant_id", nullable=False)

    # 4. Indice
    op.create_index(
        "ix_universidades_tenant_id",
        "universidades",
        ["tenant_id"],
    )

    # 5. RLS forced + policy de aislamiento por tenant
    op.execute("ALTER TABLE universidades ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE universidades FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON universidades
        USING (tenant_id = (current_setting('app.current_tenant', true))::uuid)
        """
    )
    # 6. Policy adicional: superadmin puede ver TODAS las universidades.
    # Necesaria para el selector dinamico del web-admin. Se activa cuando
    # `current_setting('app.user_roles', true)` contiene 'superadmin'
    # (lo setea `UniversidadService.list()` si user.roles incluye superadmin).
    op.execute(
        """
        CREATE POLICY superadmin_view_all ON universidades
        FOR SELECT
        USING (current_setting('app.user_roles', true) LIKE '%superadmin%')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON universidades")
    op.execute("ALTER TABLE universidades NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE universidades DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_universidades_tenant_id", table_name="universidades")
    op.drop_column("universidades", "tenant_id")
