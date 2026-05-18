"""drop tareas_practicas.ejercicios JSONB legacy

Revision ID: 20260514_0002
Revises: 20260514_0001
Create Date: 2026-05-14

ADR-047 — eliminacion del campo JSONB legacy `tareas_practicas.ejercicios`.

Los ejercicios viven ahora en la tabla `ejercicios` standalone (ADR-047)
y se asocian a TPs via `tp_ejercicios`. Esta migration completa la
deprecation del campo JSONB que se preservo en `20260514_0001` durante
el refactor del service/routes.

BC-breaking: cualquier consumer que enviara `ejercicios=[...]` en el
POST/PATCH de TP recibe un error de validacion Pydantic (campo
desconocido). Los frontends quedan rotos hasta el Batch 9 — decision
consciente del usuario (sin backward compat hacks).

Downgrade: re-crea la columna con default `[]::jsonb`. NO restaura datos
(la informacion vive en `tp_ejercicios` JOIN `ejercicios` ahora).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260514_0002"
down_revision: str | None = "20260514_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tareas_practicas", "ejercicios")


def downgrade() -> None:
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "ejercicios",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
