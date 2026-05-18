"""template brief refactor: enunciado→consigna + drops

Revision ID: 20260512_0002
Revises: 20260512_0001
Create Date: 2026-05-12

La plantilla deja de ser una copia parcial del TP y pasa a ser un BRIEF
pedagógico que sirve como prompt para que el docente (o la IA) genere el
TP en cada comisión. El fan-out automático se elimina (ver service refactor).

Cambios en `tareas_practicas_templates`:
- RENAME COLUMN `enunciado` → `consigna` (cambio de semántica: ya no es el
  enunciado del TP, es una directiva de qué debe contener el TP).
- DROP COLUMN: `inicial_codigo`, `rubrica`, `test_cases`, `ejercicios`,
  `fecha_inicio`, `fecha_fin` (todos son del nivel de instancia, no del brief).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260512_0002"
down_revision = "20260512_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tareas_practicas_templates",
        "enunciado",
        new_column_name="consigna",
    )
    op.drop_column("tareas_practicas_templates", "inicial_codigo")
    op.drop_column("tareas_practicas_templates", "rubrica")
    op.drop_column("tareas_practicas_templates", "test_cases")
    op.drop_column("tareas_practicas_templates", "ejercicios")
    op.drop_column("tareas_practicas_templates", "fecha_inicio")
    op.drop_column("tareas_practicas_templates", "fecha_fin")


def downgrade() -> None:
    op.add_column(
        "tareas_practicas_templates",
        sa.Column("fecha_fin", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tareas_practicas_templates",
        sa.Column("fecha_inicio", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tareas_practicas_templates",
        sa.Column(
            "ejercicios",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "tareas_practicas_templates",
        sa.Column(
            "test_cases",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "tareas_practicas_templates",
        sa.Column("rubrica", JSONB, nullable=True),
    )
    op.add_column(
        "tareas_practicas_templates",
        sa.Column("inicial_codigo", sa.Text(), nullable=True),
    )
    op.alter_column(
        "tareas_practicas_templates",
        "consigna",
        new_column_name="enunciado",
    )
