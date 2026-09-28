"""add_classification_reviews

Revision ID: 20260906_0006
Revises: 20260905_0005
Create Date: 2026-09-27

Tabla `classification_reviews` (B3+B5, design.md D7 + corrección D7.a/D7.b/D7.c
del DBA, 27/09/2026): revisión humana de una clasificación marcada
`needs_review`. ADITIVA — crea una tabla nueva y un índice sobre
`classifications` existente, no toca filas ni columnas existentes. RLS por
tenant vía `apply_tenant_rls` (mismo mecanismo que `interrater_ratings`,
precedente exacto: tabla con `tenant_id`, escrita por un docente vía HTTP y
no por un worker).

Dos FK nullable a `classifications.id` (D7.a): `previous_classification_id` /
`new_classification_id`. Sin ellas, reconstruir qué `Classification` resultó
de una revisión exige inferir por `episode_id` + orden temporal, y eso se
rompe con la segunda revisión que corrige a la primera.

Índice parcial B-tree (D7.c, no GIN — no hay ningún GIN en el repo) sobre
`classifications` para la consulta de la cola: filtra `is_current` + la
clave JSONB `needs_review`, y su tamaño es proporcional a los ~47 casos
retenidos, no al corpus entero (que crece ~207 filas/día). Más un índice
simple en `classification_reviews (tenant_id, episode_id)` para el
`NOT EXISTS` (anti-join) de la misma consulta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0006"
down_revision: str | None = "20260905_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_reviews",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_role", sa.String(40), nullable=False),
        sa.Column(
            "previous_classification_id",
            sa.BigInteger,
            sa.ForeignKey(
                "classifications.id", name="fk_classification_reviews_previous_classification_id"
            ),
            nullable=True,
        ),
        sa.Column(
            "new_classification_id",
            sa.BigInteger,
            sa.ForeignKey(
                "classifications.id", name="fk_classification_reviews_new_classification_id"
            ),
            nullable=True,
        ),
        sa.Column("verdict", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_classification_reviews"),
    )
    op.create_index("ix_classification_reviews_tenant_id", "classification_reviews", ["tenant_id"])
    op.create_index(
        "ix_classification_reviews_episode_id", "classification_reviews", ["episode_id"]
    )
    op.create_index(
        "ix_classification_reviews_reviewer_id", "classification_reviews", ["reviewer_id"]
    )
    op.create_index(
        "ix_classification_reviews_tenant_episode",
        "classification_reviews",
        ["tenant_id", "episode_id"],
    )
    op.execute("SELECT apply_tenant_rls('classification_reviews')")

    # D7.c: índice parcial sobre classifications para la cola de revisión.
    # NO GIN — sería el primero del repo y cubriría una consulta que nadie
    # hace, a cambio de un índice mucho más grande.
    op.execute("""
        CREATE INDEX ix_classifications_needs_review_pending
        ON classifications (comision_id, episode_id)
        WHERE is_current AND (features->>'needs_review') = 'true'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_classifications_needs_review_pending")
    op.drop_table("classification_reviews")
