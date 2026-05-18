"""add_tareas_practicas_templates

Revision ID: 20260423_0001
Revises: 20260422_0001
Create Date: 2026-04-23

Crea la tabla `tareas_practicas_templates` como fuente canónica por
(materia_id, periodo_id) y extiende `tareas_practicas` con `template_id`
(FK nullable a templates) + `has_drift` (bool) para rastrear divergencia
de la instancia respecto del template. Ver ADR-016.

- `tareas_practicas_templates`: versionado inmutable via `parent_template_id`,
  RLS por tenant_id, checks de estado/peso/version.
- `tareas_practicas.template_id`: nullable — una TP "huérfana" creada antes
  de ADR-016 (o manualmente sin template) tiene `template_id=NULL`.
- `tareas_practicas.has_drift`: si true, la instancia divergió del template
  (edición directa del enunciado/rubrica/peso/fechas/titulo). Protegido por
  CHECK `ck_tp_drift_needs_template` (no hay drift sin template).

El CTR no se toca: `Episode.problema_id` sigue apuntando a la instancia.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0001"
down_revision: str | None = "20260422_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Nueva tabla `tareas_practicas_templates` ─────────────────────
    op.create_table(
        "tareas_practicas_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("periodo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("enunciado", sa.Text, nullable=False),
        sa.Column("inicial_codigo", sa.Text, nullable=True),
        sa.Column("rubrica", postgresql.JSONB, nullable=True),
        sa.Column("peso", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("parent_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tareas_practicas_templates"),
        sa.ForeignKeyConstraint(
            ["materia_id"],
            ["materias.id"],
            name="fk_tareas_practicas_templates_materia_id_materias",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
            name="fk_tareas_practicas_templates_periodo_id_periodos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_template_id"],
            ["tareas_practicas_templates.id"],
            name="fk_tp_templates_parent_template_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "materia_id",
            "periodo_id",
            "codigo",
            "version",
            name="uq_template_codigo_version",
        ),
        sa.CheckConstraint(
            "estado IN ('draft', 'published', 'archived')",
            name="ck_template_estado",
        ),
        sa.CheckConstraint(
            "peso >= 0 AND peso <= 1",
            name="ck_template_peso",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_template_version",
        ),
    )
    op.create_index("ix_template_tenant_id", "tareas_practicas_templates", ["tenant_id"])
    op.create_index(
        "ix_template_materia_periodo",
        "tareas_practicas_templates",
        ["tenant_id", "materia_id", "periodo_id"],
    )
    op.create_index(
        "ix_template_parent",
        "tareas_practicas_templates",
        ["parent_template_id"],
    )
    op.create_index(
        "ix_template_deleted_at",
        "tareas_practicas_templates",
        ["deleted_at"],
    )

    # RLS por tenant_id (RN-001, ADR-001)
    op.execute("SELECT apply_tenant_rls('tareas_practicas_templates')")

    # ── Extender `tareas_practicas` ──────────────────────────────────
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tareas_practicas_templates.id",
                name="fk_tareas_practicas_template_id_tareas_practicas_templates",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "has_drift",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_tareas_practicas_template_id", "tareas_practicas", ["template_id"])
    op.create_check_constraint(
        "ck_tp_drift_needs_template",
        "tareas_practicas",
        "has_drift = false OR template_id IS NOT NULL",
    )

    # Auto-promoción gated por env AUTO_PROMOTE_UNIQUE_TPS — no implementada
    # por default. Ver ADR-016.


def downgrade() -> None:
    # Revertir cambios en `tareas_practicas` (orden inverso al upgrade)
    op.drop_constraint("ck_tp_drift_needs_template", "tareas_practicas", type_="check")
    op.drop_index("ix_tareas_practicas_template_id", table_name="tareas_practicas")
    op.drop_column("tareas_practicas", "has_drift")
    op.drop_column("tareas_practicas", "template_id")

    # Drop tabla `tareas_practicas_templates` (indices + constraints caen con
    # el table drop; los dropeamos explícitos para que el downgrade sea claro)
    op.drop_index("ix_template_deleted_at", table_name="tareas_practicas_templates")
    op.drop_index("ix_template_parent", table_name="tareas_practicas_templates")
    op.drop_index("ix_template_materia_periodo", table_name="tareas_practicas_templates")
    op.drop_index("ix_template_tenant_id", table_name="tareas_practicas_templates")
    op.drop_table("tareas_practicas_templates")
