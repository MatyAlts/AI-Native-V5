"""add ejercicios JSONB to tareas_practicas_templates

Revision ID: 20260512_0001
Revises: 20260507_0002
Create Date: 2026-05-12

Cierra la brecha de templates vs instancias: el fan-out a `TareaPractica`
ahora puede copiar ejercicios secuenciales (epic tp-entregas-correccion)
desde la plantilla. `test_cases` ya estaba (ADR-034); `ejercicios` faltaba.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260512_0001"
down_revision = "20260507_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tareas_practicas_templates",
        sa.Column(
            "ejercicios",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tareas_practicas_templates", "ejercicios")
