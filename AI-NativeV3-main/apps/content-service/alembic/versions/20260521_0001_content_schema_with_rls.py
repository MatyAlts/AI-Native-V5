"""content_schema_with_rls

Revision ID: 20260521_0001
Revises: 20260420_0001
Create Date: 2026-05-21

Agrega las tablas del content-service (materiales + chunks con pgvector)
a la base academic_main. Depende de la migración inicial del academic-service.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260521_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Dimensión del modelo multilingual-e5-large
EMBEDDING_DIM = 1024


def upgrade() -> None:
    # Habilitar pgvector (idempotente)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Materiales ─────────────────────────────────────────────────────
    op.create_table(
        "materiales",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No hay FK física a comisiones aunque esté en la misma base —
        # mantener la capa lógica separada para futuro split en bases propias.
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("estado", sa.String(30), nullable=False, server_default="uploaded"),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("chunks_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_materiales"),
    )
    op.create_index("ix_materiales_tenant_id", "materiales", ["tenant_id"])
    op.create_index("ix_materiales_comision_id", "materiales", ["comision_id"])
    op.create_index("ix_materiales_content_hash", "materiales", ["content_hash"])
    op.create_index("ix_materiales_deleted_at", "materiales", ["deleted_at"])
    op.create_index(
        "ix_materiales_tenant_comision",
        "materiales",
        ["tenant_id", "comision_id"],
    )

    # ── Chunks ─────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contenido", sa.Text, nullable=False),
        sa.Column("contenido_hash", sa.String(64), nullable=False),
        # embedding vector(1024) — se setea con raw SQL por el driver asyncpg
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("chunk_type", sa.String(30), nullable=False, server_default="prose"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materiales.id"],
            name="fk_chunks_material_id_materiales",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "material_id",
            "position",
            name="uq_chunks_tenant_material_position",
        ),
    )
    # Columna vector separada para que Alembic no falle al no conocer el tipo
    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({EMBEDDING_DIM})")

    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_material_id", "chunks", ["material_id"])
    op.create_index("ix_chunks_comision_id", "chunks", ["comision_id"])
    op.create_index("ix_chunks_tenant_comision", "chunks", ["tenant_id", "comision_id"])

    # Índice aproximado IVFFlat para cosine similarity
    # 100 lists: suficiente hasta ~1M chunks; re-evaluar en F5 para escala.
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # ── RLS ────────────────────────────────────────────────────────────
    # Las dos tablas son multi-tenant
    op.execute("SELECT apply_tenant_rls('materiales')")
    op.execute("SELECT apply_tenant_rls('chunks')")


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("materiales")
