"""instrumentos_research — 3 tablas para instrumentos del diseno cuasi-experimental

Revision ID: 20260517_0001
Revises: 20260515_0002
Create Date: 2026-05-17

Cierra P2-1 (pretest autoeficacia), P2-2 (cuestionario IA previa) y P2-3
(test transferencia) del PlanMejora.md como ESQUELETO TECNICO. El contenido
academico (ítems del cuestionario, ítems del pretest, problemas de transferencia)
queda marcado en seeds y placeholders como `[PENDIENTE VALIDACION COAUTORAL —
ANA GARIS]` hasta revision coautoral + comite etico UNSL.

Tablas:
1. `respuestas_cuestionario_ia` — P2-2, cuestionario inicial sobre experiencia previa con IA
2. `respuestas_pretest_autoeficacia` — P2-1, pretest estandarizado de autoeficacia
   en programacion (referencia: Lishinski et al. 2016, draft en
   docs/research/protocolo-autoeficacia-programacion.md)
3. `respuestas_test_transferencia` — P2-3, pruebas comunes para ambos grupos
   (experimental con CTR + comparacion sin CTR) — H2 del paper §6.1

Invariantes:
- Multi-tenant: RLS forzado en las 3 tablas (ADR-001 + invariante CI make check-rls)
- Idempotencia: UNIQUE (tenant_id, comision_id, student_pseudonym, instrument_version)
  en las 3. Para transferencia se suma test_id porque un mismo estudiante hace varios
  problemas.
- Versionado: `instrument_version str(20)` permite analisis estratificado por version
  cuando el contenido evolucione (pattern recomendado por exploración de patterns,
  no existía en el repo antes).
- Anonimizacion: student_pseudonym UUID, NO user_id (ADR-031 audit_aliases).

ADR de respaldo: ADR-053 (marcos interpretativos MI1-MI3 + 7 principios) +
docs/limitaciones-declaradas.md riesgos R1-R5 (Hawthorne, performatividad, deriva LLM,
brecha digital previa, sobrecarga cognitiva). Los instrumentos materializan las
mitigaciones de R1 (extension temporal + pretest baseline) y R4 (cuestionario
captura experiencia previa con IA).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260517_0001"
down_revision: str | None = "20260515_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ============================================================================
# 1. CUESTIONARIO IA PREVIA (P2-2)
# ============================================================================


def _create_cuestionario_ia() -> None:
    op.create_table(
        "respuestas_cuestionario_ia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "comision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comisiones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "instrument_version",
            sa.String(40),
            nullable=False,
            server_default="cuestionario-ia-v0.1.0-draft",
        ),
        sa.Column("responses", postgresql.JSONB, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "instrument_version",
            name="uq_resp_cuestionario_ia_estudiante",
        ),
    )
    op.create_index(
        "ix_resp_cuestionario_ia_tenant_id",
        "respuestas_cuestionario_ia",
        ["tenant_id"],
    )
    op.create_index(
        "ix_resp_cuestionario_ia_comision_id",
        "respuestas_cuestionario_ia",
        ["comision_id"],
    )
    op.create_index(
        "ix_resp_cuestionario_ia_student",
        "respuestas_cuestionario_ia",
        ["student_pseudonym"],
    )
    op.execute("ALTER TABLE respuestas_cuestionario_ia ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE respuestas_cuestionario_ia FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY resp_cuestionario_ia_tenant_isolation ON respuestas_cuestionario_ia "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


# ============================================================================
# 2. PRETEST AUTOEFICACIA (P2-1)
# ============================================================================


def _create_pretest_autoeficacia() -> None:
    op.create_table(
        "respuestas_pretest_autoeficacia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "comision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comisiones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "instrument_version",
            sa.String(40),
            nullable=False,
            server_default="lishinski-2016-es-utn-v0.1.0-draft",
        ),
        sa.Column("responses", postgresql.JSONB, nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("subscale_scores", postgresql.JSONB, nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "instrument_version",
            name="uq_resp_pretest_autoeficacia_estudiante",
        ),
    )
    op.create_index(
        "ix_resp_pretest_tenant_id",
        "respuestas_pretest_autoeficacia",
        ["tenant_id"],
    )
    op.create_index(
        "ix_resp_pretest_comision_id",
        "respuestas_pretest_autoeficacia",
        ["comision_id"],
    )
    op.create_index(
        "ix_resp_pretest_student",
        "respuestas_pretest_autoeficacia",
        ["student_pseudonym"],
    )
    op.execute("ALTER TABLE respuestas_pretest_autoeficacia ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE respuestas_pretest_autoeficacia FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY resp_pretest_tenant_isolation ON respuestas_pretest_autoeficacia "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


# ============================================================================
# 3. TEST DE TRANSFERENCIA (P2-3)
# ============================================================================


def _create_test_transferencia() -> None:
    op.create_table(
        "respuestas_test_transferencia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "comision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comisiones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "instrument_version",
            sa.String(40),
            nullable=False,
            server_default="transfer-test-v0.1.0-draft",
        ),
        # "experimental" (grupo con CTR activo) | "comparison" (grupo sin CTR)
        sa.Column("group_assignment", sa.String(20), nullable=False),
        # Identificador del problema (ej. "transfer-01", "transfer-02", ...)
        sa.Column("test_id", sa.String(50), nullable=False),
        sa.Column("correct_answer", sa.Boolean(), nullable=False),
        sa.Column("time_taken_seconds", sa.Integer(), nullable=False),
        # Respuesta detallada del estudiante (codigo, opcion elegida, etc.)
        sa.Column("response_detail", postgresql.JSONB, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        # Un estudiante responde un mismo test_id una sola vez por version
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            "test_id",
            "instrument_version",
            name="uq_resp_transfer_estudiante_test",
        ),
        # Check constraint: group_assignment debe ser uno de los dos valores
        sa.CheckConstraint(
            "group_assignment IN ('experimental', 'comparison')",
            name="ck_resp_transfer_group_assignment",
        ),
    )
    op.create_index(
        "ix_resp_transfer_tenant_id",
        "respuestas_test_transferencia",
        ["tenant_id"],
    )
    op.create_index(
        "ix_resp_transfer_comision_id",
        "respuestas_test_transferencia",
        ["comision_id"],
    )
    op.create_index(
        "ix_resp_transfer_student",
        "respuestas_test_transferencia",
        ["student_pseudonym"],
    )
    op.create_index(
        "ix_resp_transfer_group",
        "respuestas_test_transferencia",
        ["group_assignment"],
    )
    op.execute("ALTER TABLE respuestas_test_transferencia ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE respuestas_test_transferencia FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY resp_transfer_tenant_isolation ON respuestas_test_transferencia "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


# ============================================================================
# UPGRADE / DOWNGRADE
# ============================================================================


def upgrade() -> None:
    _create_cuestionario_ia()
    _create_pretest_autoeficacia()
    _create_test_transferencia()


def downgrade() -> None:
    # Revertir en orden inverso al de creacion
    op.execute(
        "DROP POLICY IF EXISTS resp_transfer_tenant_isolation ON respuestas_test_transferencia"
    )
    op.execute("ALTER TABLE respuestas_test_transferencia DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_resp_transfer_group", table_name="respuestas_test_transferencia")
    op.drop_index("ix_resp_transfer_student", table_name="respuestas_test_transferencia")
    op.drop_index("ix_resp_transfer_comision_id", table_name="respuestas_test_transferencia")
    op.drop_index("ix_resp_transfer_tenant_id", table_name="respuestas_test_transferencia")
    op.drop_table("respuestas_test_transferencia")

    op.execute(
        "DROP POLICY IF EXISTS resp_pretest_tenant_isolation ON respuestas_pretest_autoeficacia"
    )
    op.execute("ALTER TABLE respuestas_pretest_autoeficacia DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_resp_pretest_student", table_name="respuestas_pretest_autoeficacia")
    op.drop_index("ix_resp_pretest_comision_id", table_name="respuestas_pretest_autoeficacia")
    op.drop_index("ix_resp_pretest_tenant_id", table_name="respuestas_pretest_autoeficacia")
    op.drop_table("respuestas_pretest_autoeficacia")

    op.execute(
        "DROP POLICY IF EXISTS resp_cuestionario_ia_tenant_isolation ON respuestas_cuestionario_ia"
    )
    op.execute("ALTER TABLE respuestas_cuestionario_ia DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_resp_cuestionario_ia_student", table_name="respuestas_cuestionario_ia")
    op.drop_index("ix_resp_cuestionario_ia_comision_id", table_name="respuestas_cuestionario_ia")
    op.drop_index("ix_resp_cuestionario_ia_tenant_id", table_name="respuestas_cuestionario_ia")
    op.drop_table("respuestas_cuestionario_ia")
