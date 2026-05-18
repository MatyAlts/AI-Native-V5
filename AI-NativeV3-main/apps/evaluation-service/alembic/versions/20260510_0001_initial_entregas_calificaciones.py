"""initial_entregas_calificaciones

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10

Migration inicial de evaluation-service. Crea (idempotentemente) las tablas
``entregas`` y ``calificaciones`` con sus FKs, constraints, indices y
politicas RLS, en la DB compartida ``academic_main``.

Contexto historico:
- Estas tablas fueron creadas originalmente por academic-service en la
  migration ``20260506_0001_tp_entregas_correccion.py`` (epic
  tp-entregas-correccion). Por eso esta migration usa CREATE TABLE IF NOT
  EXISTS / DO blocks defensivos: en el ambiente piloto las tablas YA EXISTEN
  cuando se corre por primera vez evaluation-service.
- En un deploy fresh sin academic-service (escenario hipotetico), esta
  migration crea las tablas desde cero con la misma estructura (verificada
  contra academic-service/alembic/versions/20260506_0001).
- Owner conceptual: a partir de ahora cualquier cambio sobre estas tablas
  va por evaluation-service/alembic, no por academic-service. Esta migration
  marca esa transicion de ownership.

Tablas owned por evaluation-service:
  * entregas         (entrega del alumno, estados draft/submitted/graded/returned)
  * calificaciones   (nota docente por entrega, FK UNIQUE a entregas)

NOTA: la columna ``ejercicios JSONB`` que tambien agrego la migration
20260506_0001 vive en ``tareas_practicas`` que es OWNED por academic-service
— NO se toca aca.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260510_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # uuid_generate_v4() esta provisto por la extension uuid-ossp ya creada
    # por init-dbs.sql / migration inicial de academic. No la pedimos aca
    # para no asumir privilegios de superuser cuando este alembic corre con
    # el rol de evaluation-service.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── entregas ──────────────────────────────────────────────────────
    if "entregas" not in existing_tables:
        op.create_table(
            "entregas",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tarea_practica_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("estado", sa.String(20), nullable=False, server_default="draft"),
            sa.Column(
                "ejercicio_estados",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_entregas"),
            sa.ForeignKeyConstraint(
                ["tarea_practica_id"],
                ["tareas_practicas.id"],
                name="fk_entregas_tarea_practica_id_tareas_practicas",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["comision_id"],
                ["comisiones.id"],
                name="fk_entregas_comision_id_comisiones",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "tarea_practica_id",
                "student_pseudonym",
                name="uq_entrega_student_tp",
            ),
            sa.CheckConstraint(
                "estado IN ('draft', 'submitted', 'graded', 'returned')",
                name="ck_entregas_estado",
            ),
        )
        op.create_index("ix_entregas_tenant_id", "entregas", ["tenant_id"])
        op.create_index(
            "ix_entregas_tarea_practica_id", "entregas", ["tarea_practica_id"]
        )
        op.create_index(
            "ix_entregas_student_pseudonym", "entregas", ["student_pseudonym"]
        )
        op.create_index("ix_entregas_comision_id", "entregas", ["comision_id"])
        op.create_index("ix_entregas_deleted_at", "entregas", ["deleted_at"])

        # RLS — mismo patron que el resto de academic_main.
        op.execute("ALTER TABLE entregas ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE entregas FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY entregas_tenant_isolation ON entregas "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )

    # ── calificaciones ────────────────────────────────────────────────
    if "calificaciones" not in existing_tables:
        op.create_table(
            "calificaciones",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("entrega_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("graded_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("nota_final", sa.Numeric(5, 2), nullable=False),
            sa.Column("feedback_general", sa.Text(), nullable=True),
            sa.Column(
                "detalle_criterios",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "graded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_calificaciones"),
            sa.ForeignKeyConstraint(
                ["entrega_id"],
                ["entregas.id"],
                name="fk_calificaciones_entrega_id_entregas",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "entrega_id", name="uq_calificaciones_entrega_id"
            ),
            sa.CheckConstraint(
                "nota_final >= 0 AND nota_final <= 10",
                name="ck_calificaciones_nota",
            ),
        )
        op.create_index(
            "ix_calificaciones_tenant_id", "calificaciones", ["tenant_id"]
        )
        op.create_index(
            "ix_calificaciones_entrega_id", "calificaciones", ["entrega_id"]
        )
        op.create_index(
            "ix_calificaciones_deleted_at", "calificaciones", ["deleted_at"]
        )

        op.execute("ALTER TABLE calificaciones ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE calificaciones FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY calificaciones_tenant_isolation ON calificaciones "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    # Cuidado: si bajamos esta migration en el ambiente piloto destruimos
    # data real (las tablas fueron creadas por academic-service y tienen
    # entregas/calificaciones reales). El downgrade aca solo tiene sentido
    # en deploys fresh donde evaluation-service creo las tablas. Preservamos
    # la simetria por convencion alembic, pero el operador deberia validar
    # ANTES de bajar.
    op.execute(
        "DROP POLICY IF EXISTS calificaciones_tenant_isolation ON calificaciones"
    )
    op.drop_table("calificaciones")

    op.execute("DROP POLICY IF EXISTS entregas_tenant_isolation ON entregas")
    op.drop_table("entregas")
