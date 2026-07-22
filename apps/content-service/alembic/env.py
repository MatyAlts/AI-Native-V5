"""Alembic environment del content-service."""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from content_service.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Indices ANN de pgvector: los crea DDL cruda (`op.execute`), no `op.create_index`
# — SQLAlchemy no puede representar `USING ivfflat (embedding vector_cosine_ops)
# WITH (lists=100)` como un Index() comparable, asi que autogenerate SIEMPRE los
# ve como drift y propone dropearlos.
#
# Aplicar esa migracion dropea el indice ANN y rompe (o degrada a seq scan sobre
# 1024 dimensiones) el retrieval semantico del RAG. Verificado 2026-07-20 contra
# pg_indexes: `CREATE INDEX ix_chunks_embedding ON chunks USING ivfflat
# (embedding vector_cosine_ops) WITH (lists='100')`, creado en la migration
# 20260521_0001_content_schema_with_rls.py:125-128.
_PGVECTOR_ANN_INDEXES = frozenset({"ix_chunks_embedding"})


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Excluye del autogenerate los indices vectoriales de pgvector."""
    return not (type_ == "index" and name in _PGVECTOR_ANN_INDEXES)


def get_url() -> str:
    return os.environ.get(
        "CONTENT_DB_URL",
        "postgresql+asyncpg://content_user:content_pass@localhost:5432/content_db",
    )


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
