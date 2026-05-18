"""ejercicio como entidad de primera clase reusable

Revision ID: 20260514_0001
Revises: 20260512_0002
Create Date: 2026-05-14

ADR-047 + ADR-048: tabla `ejercicios` standalone con UUID propio y
schema pedagogico rico (campos PID-UTN). Tabla intermedia `tp_ejercicios`
para asociacion N:M con `tareas_practicas`.

Esta migration es ADITIVA: NO dropea `tareas_practicas.ejercicios`
JSONB todavia. La eliminacion del campo legacy ocurre en una migration
posterior una vez que el service / routes / frontends esten refactoreados
para consumir las tablas nuevas. Esto evita romper HEAD durante el
refactor cross-service.

Tablas:
1. `ejercicios` — entidad standalone con todos los campos del schema
   pedagogico PID-UTN como columnas JSONB tipadas (ver ADR-048).
2. `tp_ejercicios` — asociacion N:M entre TareaPractica y Ejercicio
   con `orden` y `peso_en_tp` propios de la relacion.

Constraints:
- UNIQUE `(tenant_id, tarea_practica_id, ejercicio_id)` — un ejercicio
  aparece a lo sumo una vez por TP.
- UNIQUE `(tenant_id, tarea_practica_id, orden)` — orden unico dentro
  de la TP.
- CHECK `peso_en_tp > 0 AND peso_en_tp <= 1`.
- CHECK `unidad_tematica IN ('secuenciales', 'condicionales',
  'repetitivas', 'mixtos')`.
- CHECK `dificultad IS NULL OR dificultad IN ('basica', 'intermedia',
  'avanzada')`.

RLS:
- `ejercicios` y `tp_ejercicios` con ENABLE + FORCE ROW LEVEL SECURITY
  (CI gate `make check-rls`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0001"
down_revision: str | None = "20260512_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. CREATE TABLE ejercicios ─────────────────────────────────
    op.create_table(
        "ejercicios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Identificacion ─────────────────────────────────────────
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("enunciado_md", sa.Text(), nullable=False),
        sa.Column("inicial_codigo", sa.Text(), nullable=True),
        # ── Clasificacion pedagogica ──────────────────────────────
        sa.Column("unidad_tematica", sa.String(30), nullable=False),
        sa.Column("dificultad", sa.String(20), nullable=True),
        sa.Column(
            "prerequisitos",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # ── Tests ejecutables (mismo formato que ADR-034) ─────────
        sa.Column(
            "test_cases",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # ── Evaluacion ────────────────────────────────────────────
        sa.Column("rubrica", postgresql.JSONB, nullable=True),
        # ── Pedagogia PID-UTN (ADR-048) ───────────────────────────
        sa.Column("tutor_rules", postgresql.JSONB, nullable=True),
        sa.Column("banco_preguntas", postgresql.JSONB, nullable=True),
        sa.Column(
            "misconceptions",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "respuesta_pista",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("heuristica_cierre", postgresql.JSONB, nullable=True),
        sa.Column(
            "anti_patrones",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # ── Autoria ──────────────────────────────────────────────
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_via_ai",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        # ── Timestamps ───────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # ── Check constraints ────────────────────────────────────
        sa.CheckConstraint(
            "unidad_tematica IN ('secuenciales', 'condicionales', 'repetitivas', 'mixtos')",
            name="ck_ejercicios_unidad_tematica",
        ),
        sa.CheckConstraint(
            "dificultad IS NULL OR dificultad IN ('basica', 'intermedia', 'avanzada')",
            name="ck_ejercicios_dificultad",
        ),
    )

    op.create_index("ix_ejercicios_tenant_id", "ejercicios", ["tenant_id"])
    op.create_index("ix_ejercicios_unidad_tematica", "ejercicios", ["unidad_tematica"])
    op.create_index("ix_ejercicios_dificultad", "ejercicios", ["dificultad"])
    op.create_index("ix_ejercicios_created_by", "ejercicios", ["created_by"])
    op.create_index("ix_ejercicios_deleted_at", "ejercicios", ["deleted_at"])

    # RLS para ejercicios
    op.execute("ALTER TABLE ejercicios ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ejercicios FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ejercicios_tenant_isolation ON ejercicios "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )

    # ── 2. CREATE TABLE tp_ejercicios ──────────────────────────────
    op.create_table(
        "tp_ejercicios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tarea_practica_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tareas_practicas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ejercicio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ejercicios.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("peso_en_tp", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        # ── Unique constraints ───────────────────────────────────
        sa.UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "ejercicio_id",
            name="uq_tp_ejercicio_pair",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "tarea_practica_id",
            "orden",
            name="uq_tp_ejercicio_orden",
        ),
        # ── Check constraints ────────────────────────────────────
        sa.CheckConstraint(
            "peso_en_tp > 0 AND peso_en_tp <= 1",
            name="ck_tp_ejercicios_peso",
        ),
        sa.CheckConstraint(
            "orden >= 1",
            name="ck_tp_ejercicios_orden",
        ),
    )

    op.create_index("ix_tp_ejercicios_tenant_id", "tp_ejercicios", ["tenant_id"])
    op.create_index(
        "ix_tp_ejercicios_tarea_practica_id", "tp_ejercicios", ["tarea_practica_id"]
    )
    op.create_index("ix_tp_ejercicios_ejercicio_id", "tp_ejercicios", ["ejercicio_id"])

    # RLS para tp_ejercicios
    op.execute("ALTER TABLE tp_ejercicios ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tp_ejercicios FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tp_ejercicios_tenant_isolation ON tp_ejercicios "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )


def downgrade() -> None:
    # Revertir en orden inverso (tp_ejercicios primero por FK a ejercicios)
    op.execute("DROP POLICY IF EXISTS tp_ejercicios_tenant_isolation ON tp_ejercicios")
    op.execute("ALTER TABLE tp_ejercicios DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_tp_ejercicios_ejercicio_id", table_name="tp_ejercicios")
    op.drop_index("ix_tp_ejercicios_tarea_practica_id", table_name="tp_ejercicios")
    op.drop_index("ix_tp_ejercicios_tenant_id", table_name="tp_ejercicios")
    op.drop_table("tp_ejercicios")

    op.execute("DROP POLICY IF EXISTS ejercicios_tenant_isolation ON ejercicios")
    op.execute("ALTER TABLE ejercicios DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_ejercicios_deleted_at", table_name="ejercicios")
    op.drop_index("ix_ejercicios_created_by", table_name="ejercicios")
    op.drop_index("ix_ejercicios_dificultad", table_name="ejercicios")
    op.drop_index("ix_ejercicios_unidad_tematica", table_name="ejercicios")
    op.drop_index("ix_ejercicios_tenant_id", table_name="ejercicios")
    op.drop_table("ejercicios")
