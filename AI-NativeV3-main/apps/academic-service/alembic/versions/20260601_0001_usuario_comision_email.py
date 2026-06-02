"""usuario_comision por email — el admin asigna docente por email, user_id se resuelve al login

Revision ID: 20260601_0001
Revises: 20260528_0001
Create Date: 2026-06-01

El admin asigna un docente a una comision por su EMAIL (el docente todavia no
se logueo, no hay user_id). La columna `email` queda como ancla persistente de
la asignacion y `user_id` pasa a nullable: se completa en el primer login del
docente con Clerk (matching por email). Alineado con student_profiles
(20260528_0001) que ya mapea email -> identidad del alumno.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0001"
down_revision: str | None = "20260528_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usuarios_comision",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.alter_column(
        "usuarios_comision",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_index(
        "ix_usuarios_comision_email",
        "usuarios_comision",
        ["email"],
    )


def downgrade() -> None:
    op.drop_index("ix_usuarios_comision_email", table_name="usuarios_comision")
    op.alter_column(
        "usuarios_comision",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("usuarios_comision", "email")
