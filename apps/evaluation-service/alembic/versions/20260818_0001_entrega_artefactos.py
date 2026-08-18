"""entrega_artefactos — el código que el alumno entregó, por ejercicio

Hasta acá `entregas` guardaba QUIÉN entregó y CUÁNDO, pero no QUÉ: ninguna
columna con el código. Lo único que existía era el snapshot del último evento
`edicion_codigo` del CTR, que se ingesta de forma asíncrona (el endpoint
devuelve 202 y un worker escribe después) y que el editor emite
fire-and-forget. Un artefacto armado leyendo eso en el momento de corregir
certifica "esto es lo que leí cuando lo pedí", no "esto es lo que el alumno
entregó" — y esa distinción importa cuando el número termina en un legajo.

Una fila por ejercicio, no un blob: la corrección asistida es por ejercicio
(ver `openspec/changes/correccion-activeia/design.md`, D1), así que cada
ejercicio necesita su propio código y su propio hash.

`entregas.artefacto_sha256` guarda el hash del conjunto, y `legacy` marca las
entregas anteriores a este cambio, que nunca van a tener snapshot del submit.

RLS con FORCE desde el minuto cero: el FORCE ya se olvidó una vez en este
mismo servicio y tiene una migration entera dedicada a repararlo
(`academic-service/.../20260507_0001_force_rls_byok_entregas_calificaciones.py`).

Revision ID: 20260818_0001
Revises: 20260711_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0001"
down_revision: str | None = "20260711_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # ── entrega_artefactos ────────────────────────────────────────────
    if "entrega_artefactos" not in existing_tables:
        op.create_table(
            "entrega_artefactos",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("entrega_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("orden", sa.Integer(), nullable=False),
            # El episodio del que salió este ejercicio. Nullable porque la TP
            # monolítica (sin ejercicioContext) no lo tiene resuelto todavía.
            sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("ejercicio_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("codigo", sa.Text(), nullable=False),
            sa.Column("language", sa.String(length=20), nullable=False, server_default="python"),
            # sha256 hex de este código. Se guarda, NUNCA se recalcula al leer:
            # si se recalculara, un cambio silencioso del contenido pasaría
            # desapercibido y el hash dejaría de probar nada.
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_entrega_artefactos"),
            sa.ForeignKeyConstraint(
                ["entrega_id"],
                ["entregas.id"],
                name="fk_entrega_artefactos_entrega",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "entrega_id",
                "orden",
                name="uq_entrega_artefacto_orden",
            ),
            sa.CheckConstraint("orden >= 1", name="ck_entrega_artefactos_orden"),
        )
        op.create_index("ix_entrega_artefactos_tenant_id", "entrega_artefactos", ["tenant_id"])
        op.create_index("ix_entrega_artefactos_entrega_id", "entrega_artefactos", ["entrega_id"])

        op.execute("ALTER TABLE entrega_artefactos ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE entrega_artefactos FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY entrega_artefactos_tenant_isolation ON entrega_artefactos "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )

    # ── columnas nuevas en entregas ───────────────────────────────────
    existing_cols = {c["name"] for c in inspector.get_columns("entregas")}

    if "artefacto_sha256" not in existing_cols:
        op.add_column(
            "entregas",
            sa.Column("artefacto_sha256", sa.String(length=64), nullable=True),
        )

    if "legacy" not in existing_cols:
        # Default TRUE en el ADD para que TODA fila existente quede marcada
        # legacy sin un UPDATE aparte; después se baja el default a FALSE para
        # que las entregas nuevas nazcan no-legacy.
        op.add_column(
            "entregas",
            sa.Column(
                "legacy",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
        op.alter_column("entregas", "legacy", server_default=sa.text("false"))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_cols = {c["name"] for c in inspector.get_columns("entregas")}
    if "legacy" in existing_cols:
        op.drop_column("entregas", "legacy")
    if "artefacto_sha256" in existing_cols:
        op.drop_column("entregas", "artefacto_sha256")

    if "entrega_artefactos" in set(inspector.get_table_names()):
        op.execute(
            "DROP POLICY IF EXISTS entrega_artefactos_tenant_isolation ON entrega_artefactos"
        )
        op.drop_index("ix_entrega_artefactos_entrega_id", table_name="entrega_artefactos")
        op.drop_index("ix_entrega_artefactos_tenant_id", table_name="entrega_artefactos")
        op.drop_table("entrega_artefactos")
