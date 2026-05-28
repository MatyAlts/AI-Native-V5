"""student_profile — mapeo pseudonym -> nombre real del alumno (auto-llenado desde Clerk)

Revision ID: 20260528_0001
Revises: 20260517_0001
Create Date: 2026-05-28

Tabla operacional separada del CTR. El CTR sigue siendo anonimo (solo
student_pseudonym). Esta tabla guarda el nombre real que el alumno expone
voluntariamente al loguearse con Clerk; solo el docente de su comision
puede leerlo (RLS por tenant_id + check de rol a nivel endpoint).

Auto-llenado: el web-student hace POST /api/v1/users/me/profile con
{full_name, email} obtenidos de Clerk al iniciar sesion. El docente no
carga CSVs.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0001"
down_revision: str | None = "20260517_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_student_profiles_tenant_id",
        "student_profiles",
        ["tenant_id"],
    )

    op.execute("ALTER TABLE student_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE student_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY student_profiles_tenant_isolation ON student_profiles "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS student_profiles_tenant_isolation ON student_profiles")
    op.execute("ALTER TABLE student_profiles DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_student_profiles_tenant_id", table_name="student_profiles")
    op.drop_table("student_profiles")
