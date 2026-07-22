"""tarea_practica.permite_pausa — el docente decide por TP si el alumno puede pausar/retomar

Revision ID: 20260615_0002
Revises: 20260615_0001
Create Date: 2026-06-15

El alumno puede abandonar un episodio y retomarlo después (ADR-025/055). Este
flag deja que el docente decida POR TP si esa pausa voluntaria está permitida:
con `permite_pausa=false` el botón "Seguir después" no aparece y el resume de un
episodio pausado se rechaza (409 en tutor-service), forzando a completar la TP
en una sola sesión (ej. evaluaciones). `server_default=true` → retrocompat: las
TPs existentes y el comportamiento actual (pausa permitida) se preservan. Boolean
simple en una tabla que ya tiene RLS por tenant — no requiere policy nueva.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260615_0002"
down_revision: str | None = "20260615_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tareas_practicas",
        sa.Column(
            "permite_pausa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tareas_practicas", "permite_pausa")
