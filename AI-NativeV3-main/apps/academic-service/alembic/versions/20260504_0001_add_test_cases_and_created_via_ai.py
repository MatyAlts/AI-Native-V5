"""add_test_cases_and_created_via_ai

Revision ID: 20260504_0001
Revises: 20260430_0001
Create Date: 2026-05-04

Agrega columnas de la epic ai-native-completion-and-byok / Sec 9 (sandbox-test-cases)
y Sec 11 (tp-generator-ai):

1. `tareas_practicas.test_cases JSONB DEFAULT '[]'::jsonb`
2. `tareas_practicas_templates.test_cases JSONB DEFAULT '[]'::jsonb`
3. `tareas_practicas.created_via_ai BOOLEAN DEFAULT FALSE`

Cada test case en el JSONB tiene shape:
  {
    "id": "uuid",
    "name": "string",
    "type": "stdin_stdout" | "pytest_assert",
    "code": "string",
    "expected": "string",
    "is_public": bool,
    "weight": int >= 1
  }

ADR-034 declara JSONB como decision (vs tabla separada) por: (a) volumen
chico (<20 tests por TP es lo esperable), (b) versionado de TP requiere
clonar test_cases en cada nueva version — JSONB hace eso trivial sin FK
chains, (c) los tests son metadata pedagogica, no entidades de primer nivel
queryables. Threshold para migrar a tabla: si una TP empieza a tener >50
tests o si el frontend necesita queries cross-TP por test_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260504_0001"
down_revision: str | None = "20260430_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. tareas_practicas.test_cases
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "test_cases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 2. tareas_practicas_templates.test_cases
    op.add_column(
        "tareas_practicas_templates",
        sa.Column(
            "test_cases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 3. tareas_practicas.created_via_ai
    # Sec 11: el wizard TP-gen IA del web-teacher seteara este flag al
    # publicar la TP editada. ADR-036 cubre la decision (caller =
    # academic-service, audit log via structlog separado del CTR).
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "created_via_ai",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tareas_practicas", "created_via_ai")
    op.drop_column("tareas_practicas_templates", "test_cases")
    op.drop_column("tareas_practicas", "test_cases")
