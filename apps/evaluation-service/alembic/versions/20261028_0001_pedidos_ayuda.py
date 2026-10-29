"""pedidos_ayuda — el alumno le pide ayuda a los docentes de su comision

Tabla nueva y aditiva: nada existente cambia. Vive fuera de la traza cognitiva:
`episode_id` es un UUID suelto SIN FK (los episodios estan en `ctr_store`, otra
base, y en el caso "Episode no encontrado" ni existen: guardarlo tal cual es el
dato para diagnosticar).

`comision_id` la deriva el servidor de la TP. `entrega_id` tiene FK a `entregas`
con `ON DELETE SET NULL`: borrar una entrega no debe borrar el pedido.

RLS `ENABLE` + `FORCE` + policy por tenant, misma receta que `correcciones_ia`.
El aislamiento por comision va en la aplicacion, como en `entregas`.

Idempotente como `20260818_0003`: si la tabla ya existe, no hace nada.

Revision ID: 20261028_0001
Revises: 20260902_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0001"
down_revision: str | None = "20260902_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if "pedidos_ayuda" in set(sa.inspect(conn).get_table_names()):
        return

    op.create_table(
        "pedidos_ayuda",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_pseudonym", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tarea_practica_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entrega_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ejercicio_orden", sa.Integer(), nullable=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("categoria", sa.String(length=30), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=True),
        sa.Column(
            "contexto", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="pendiente"),
        sa.Column("resuelto_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resuelto_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pedidos_ayuda"),
        sa.ForeignKeyConstraint(
            ["entrega_id"],
            ["entregas.id"],
            name="fk_pedidos_ayuda_entrega_id_entregas",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "categoria IN ('no_puedo_avanzar', 'error_plataforma', 'duda_consigna', 'otro')",
            name="categoria",
        ),
        sa.CheckConstraint("estado IN ('pendiente', 'resuelto')", name="estado"),
        sa.CheckConstraint("mensaje IS NULL OR char_length(mensaje) <= 1000", name="mensaje"),
        sa.CheckConstraint(
            "(estado = 'resuelto') = (resuelto_at IS NOT NULL)",
            name="resuelto_coherente",
        ),
    )
    # Lista del docente (por comision y estado) y anti-spam / "mis pedidos".
    op.create_index(
        "ix_pedidos_ayuda_comision_estado",
        "pedidos_ayuda",
        ["tenant_id", "comision_id", "estado", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_pedidos_ayuda_alumno",
        "pedidos_ayuda",
        ["tenant_id", "student_pseudonym", sa.text("created_at DESC")],
    )

    op.execute("ALTER TABLE pedidos_ayuda ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pedidos_ayuda FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY pedidos_ayuda_tenant_isolation ON pedidos_ayuda "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "pedidos_ayuda" in set(sa.inspect(conn).get_table_names()):
        op.execute("DROP POLICY IF EXISTS pedidos_ayuda_tenant_isolation ON pedidos_ayuda")
        op.drop_table("pedidos_ayuda")
