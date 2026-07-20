"""initial_schema_with_rls

Revision ID: 20260420_0001
Revises:
Create Date: 2026-04-20

Crea todas las tablas del dominio académico en su estructura inicial
y aplica la política RLS a cada tabla con tenant_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260420_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES_WITH_TENANT_ID = [
    "facultades",
    "carreras",
    "planes_estudio",
    "materias",
    "periodos",
    "comisiones",
    "inscripciones",
    "usuarios_comision",
    "audit_log",
]


def upgrade() -> None:
    # Asegurar extensiones
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── Universidad (tenant raíz, sin tenant_id) ─────────────────────
    op.create_table(
        "universidades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("dominio_email", sa.String(200), nullable=True),
        sa.Column("keycloak_realm", sa.String(100), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_universidades"),
        sa.UniqueConstraint("codigo", name="uq_universidades_codigo"),
        sa.UniqueConstraint("keycloak_realm", name="uq_universidades_keycloak_realm"),
    )
    op.create_index("ix_universidades_deleted_at", "universidades", ["deleted_at"])

    # ── Facultades ────────────────────────────────────────────────────
    op.create_table(
        "facultades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universidad_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("decano_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_facultades"),
        sa.ForeignKeyConstraint(
            ["universidad_id"],
            ["universidades.id"],
            name="fk_facultades_universidad_id_universidades",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_facultad_tenant_codigo"),
    )
    op.create_index("ix_facultades_tenant_id", "facultades", ["tenant_id"])
    op.create_index("ix_facultades_universidad_id", "facultades", ["universidad_id"])
    op.create_index("ix_facultades_deleted_at", "facultades", ["deleted_at"])

    # ── Carreras ──────────────────────────────────────────────────────
    op.create_table(
        "carreras",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("universidad_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facultad_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("duracion_semestres", sa.Integer, nullable=False, server_default="8"),
        sa.Column("modalidad", sa.String(30), nullable=False, server_default="presencial"),
        sa.Column("director_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_carreras"),
        sa.ForeignKeyConstraint(
            ["universidad_id"],
            ["universidades.id"],
            name="fk_carreras_universidad_id_universidades",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["facultad_id"],
            ["facultades.id"],
            name="fk_carreras_facultad_id_facultades",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_carrera_tenant_codigo"),
    )
    op.create_index("ix_carreras_tenant_id", "carreras", ["tenant_id"])
    op.create_index("ix_carreras_universidad_id", "carreras", ["universidad_id"])
    op.create_index("ix_carreras_facultad_id", "carreras", ["facultad_id"])
    op.create_index("ix_carreras_deleted_at", "carreras", ["deleted_at"])

    # ── Planes de estudio ─────────────────────────────────────────────
    op.create_table(
        "planes_estudio",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("año_inicio", sa.Integer, nullable=False),
        sa.Column("ordenanza", sa.String(100), nullable=True),
        sa.Column("vigente", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_planes_estudio"),
        sa.ForeignKeyConstraint(
            ["carrera_id"],
            ["carreras.id"],
            name="fk_planes_estudio_carrera_id_carreras",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "carrera_id", "version", name="uq_plan_version"),
    )
    op.create_index("ix_planes_estudio_tenant_id", "planes_estudio", ["tenant_id"])
    op.create_index("ix_planes_estudio_carrera_id", "planes_estudio", ["carrera_id"])
    op.create_index("ix_planes_estudio_deleted_at", "planes_estudio", ["deleted_at"])

    # ── Materias ──────────────────────────────────────────────────────
    op.create_table(
        "materias",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("horas_totales", sa.Integer, nullable=False, server_default="96"),
        sa.Column("cuatrimestre_sugerido", sa.Integer, nullable=False, server_default="1"),
        sa.Column("objetivos", sa.Text, nullable=True),
        sa.Column("correlativas_cursar", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("correlativas_rendir", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_materias"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["planes_estudio.id"],
            name="fk_materias_plan_id_planes_estudio",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "plan_id", "codigo", name="uq_materia_codigo"),
    )
    op.create_index("ix_materias_tenant_id", "materias", ["tenant_id"])
    op.create_index("ix_materias_plan_id", "materias", ["plan_id"])
    op.create_index("ix_materias_deleted_at", "materias", ["deleted_at"])

    # ── Periodos ──────────────────────────────────────────────────────
    op.create_table(
        "periodos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("fecha_inicio", sa.Date, nullable=False),
        sa.Column("fecha_fin", sa.Date, nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="abierto"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_periodos"),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_periodo_tenant_codigo"),
    )
    op.create_index("ix_periodos_tenant_id", "periodos", ["tenant_id"])
    op.create_index("ix_periodos_deleted_at", "periodos", ["deleted_at"])

    # ── Comisiones ────────────────────────────────────────────────────
    op.create_table(
        "comisiones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("materia_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("periodo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("cupo_maximo", sa.Integer, nullable=False, server_default="50"),
        sa.Column("horario", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("curso_config_hash", sa.String(64), nullable=True),
        sa.Column(
            "ai_budget_monthly_usd", sa.Numeric(10, 2), nullable=False, server_default="100.00"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_comisiones"),
        sa.ForeignKeyConstraint(
            ["materia_id"],
            ["materias.id"],
            name="fk_comisiones_materia_id_materias",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
            name="fk_comisiones_periodo_id_periodos",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "materia_id",
            "periodo_id",
            "codigo",
            name="uq_comision_codigo",
        ),
    )
    op.create_index("ix_comisiones_tenant_id", "comisiones", ["tenant_id"])
    op.create_index("ix_comisiones_materia_id", "comisiones", ["materia_id"])
    op.create_index("ix_comisiones_periodo_id", "comisiones", ["periodo_id"])
    op.create_index("ix_comisiones_deleted_at", "comisiones", ["deleted_at"])

    # ── Inscripciones ─────────────────────────────────────────────────
    op.create_table(
        "inscripciones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False, server_default="regular"),
        sa.Column("estado", sa.String(20), nullable=False, server_default="activa"),
        sa.Column("fecha_inscripcion", sa.Date, nullable=False),
        sa.Column("nota_final", sa.Numeric(5, 2), nullable=True),
        sa.Column("fecha_cierre", sa.Date, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_inscripciones"),
        sa.ForeignKeyConstraint(
            ["comision_id"],
            ["comisiones.id"],
            name="fk_inscripciones_comision_id_comisiones",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "student_pseudonym",
            name="uq_inscripcion_student",
        ),
    )
    op.create_index("ix_inscripciones_tenant_id", "inscripciones", ["tenant_id"])
    op.create_index("ix_inscripciones_comision_id", "inscripciones", ["comision_id"])
    op.create_index("ix_inscripciones_student_pseudonym", "inscripciones", ["student_pseudonym"])
    op.create_index("ix_inscripciones_deleted_at", "inscripciones", ["deleted_at"])

    # ── Usuarios_Comision ─────────────────────────────────────────────
    op.create_table(
        "usuarios_comision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("permisos_extra", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("fecha_desde", sa.Date, nullable=False),
        sa.Column("fecha_hasta", sa.Date, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios_comision"),
        sa.ForeignKeyConstraint(
            ["comision_id"],
            ["comisiones.id"],
            name="fk_usuarios_comision_comision_id_comisiones",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "comision_id",
            "user_id",
            "rol",
            name="uq_usuario_comision",
        ),
    )
    op.create_index("ix_usuarios_comision_tenant_id", "usuarios_comision", ["tenant_id"])
    op.create_index("ix_usuarios_comision_comision_id", "usuarios_comision", ["comision_id"])

    # ── Audit log ─────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changes", postgresql.JSONB, nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_resource_id", "audit_log", ["resource_id"])
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])

    # ── Casbin rules ──────────────────────────────────────────────────
    op.create_table(
        "casbin_rules",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("ptype", sa.String(10), nullable=False),
        sa.Column("v0", sa.String(256), nullable=True),
        sa.Column("v1", sa.String(256), nullable=True),
        sa.Column("v2", sa.String(256), nullable=True),
        sa.Column("v3", sa.String(256), nullable=True),
        sa.Column("v4", sa.String(256), nullable=True),
        sa.Column("v5", sa.String(256), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_casbin_rules"),
    )
    op.create_index("ix_casbin_rules_v0", "casbin_rules", ["v0"])
    op.create_index("ix_casbin_rules_v1", "casbin_rules", ["v1"])
    op.create_index("ix_casbin_rules_v2", "casbin_rules", ["v2"])

    # ── Aplicar RLS a todas las tablas multi-tenant ──────────────────
    for table in TABLES_WITH_TENANT_ID:
        op.execute(f"SELECT apply_tenant_rls('{table}')")


def downgrade() -> None:
    op.drop_table("casbin_rules")
    op.drop_table("audit_log")
    op.drop_table("usuarios_comision")
    op.drop_table("inscripciones")
    op.drop_table("comisiones")
    op.drop_table("periodos")
    op.drop_table("materias")
    op.drop_table("planes_estudio")
    op.drop_table("carreras")
    op.drop_table("facultades")
    op.drop_table("universidades")
