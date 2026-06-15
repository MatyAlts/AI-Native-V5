"""drop tabla huerfana casbin_rule (singular)

Revision ID: 20260615_0001
Revises: 20260611_0001
Create Date: 2026-06-15

En `academic_main` coexisten dos tablas Casbin: `casbin_rule` (singular) y
`casbin_rules` (plural). La canonica que usa la app es la PLURAL — modelo
`CasbinRule.__tablename__ = "casbin_rules"` (models/transversal.py) y el
adapter `casbin_setup.py` la fija con `db_class=CasbinRule` +
`create_all_models=False`. La SINGULAR es un artefacto huerfano: el default
de `casbin_sqlalchemy_adapter` crea `casbin_rule` cuando se instancia sin
`db_class` (cosa que NO hacemos). Quedo creada en algun bootstrap viejo y
nunca se escribe/lee desde el codigo vivo.

Verificado por grep: NINGUN codigo vivo referencia `casbin_rule` singular
(seeds, modelos, adapter y migrations usan exclusivamente `casbin_rules`).

Esta migration la dropea para dejar el schema limpio y evitar confusion en
auditorias. `DROP TABLE IF EXISTS` es idempotente — no falla si la tabla ya
no existe (entornos donde nunca se materializo).

Downgrade: no-op documentado. La libreria `casbin_sqlalchemy_adapter`
recrea `casbin_rule` automaticamente SOLO si se vuelve al default
`create_all_models=True` (lo que NO hacemos — ver casbin_setup.py). No hay
datos que restaurar: la tabla estaba huerfana, sin escrituras de la app.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260615_0001"
down_revision: str | None = "20260611_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS casbin_rule")


def downgrade() -> None:
    # No-op documentado: la tabla era huerfana (sin datos de la app). La
    # libreria solo la recrearia bajo `create_all_models=True`, default que
    # el adapter NO usa. No hay nada que restaurar.
    pass
