"""universidades: policy authenticated_can_list para selector de teacher/student

Revision ID: 20260515_0001
Revises: 20260514_0004
Create Date: 2026-05-15

Permite que docentes y alumnos listen TODAS las universidades (solo metadata
publica: nombre + codigo) para el `TenantSelector` de los frontends
web-teacher y web-student. Hoy con la policy `tenant_isolation`, un docente
en tenant X solo veria su propia universidad, lo que rompe el caso real de
docentes que dictan en varias universidades (caso comun: convenios entre
UTN-FRM y UTN-FRSN, profesor invitado, etc.).

Decision de seguridad: listar nombres+codigos de universidades NO es leak
critico — son metadata institucional publica. El aislamiento real esta en
las demas tablas (facultades, comisiones, ejercicios) que mantienen RLS
estricta por tenant_id.

Cuando llegue Keycloak con multi-tenancy real (gap B.2), este endpoint
debera filtrar por `usuarios_comision.user_id` (para docentes) y
`inscripciones.student_pseudonym` (para alumnos) para mostrar solo las
universidades donde el caller tiene rol activo.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260515_0001"
down_revision: str | Sequence[str] | None = "20260514_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Policy: cualquier user con tenant seteado puede listar (SELECT) todas las unis.
    # Combinada con `tenant_isolation` y `superadmin_view_all` por OR de Postgres RLS.
    op.execute(
        """
        CREATE POLICY authenticated_can_list ON universidades
        FOR SELECT
        USING (current_setting('app.current_tenant', true) IS NOT NULL
               AND current_setting('app.current_tenant', true) <> '')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS authenticated_can_list ON universidades")
