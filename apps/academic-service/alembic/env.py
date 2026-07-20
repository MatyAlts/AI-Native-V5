"""Alembic environment: corre migraciones online/offline con async engine."""

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

# Add src to path for imports
SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from academic_service.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tablas que VIVEN en academic_main pero cuyo modelo SQLAlchemy pertenece a OTRO
# servicio. academic-service no las tiene en su metadata, asi que sin este filtro
# `alembic revision --autogenerate` las lee de la DB, no las encuentra en el
# metadata y propone `op.drop_table(...)` — con los datos adentro.
#
# Verificado 2026-07-20 con `alembic check`: proponia dropear entregas,
# calificaciones, byok_keys, byok_keys_usage y alembic_version_evaluation.
#
# Es el espejo del `include_object` que evaluation-service ya tiene (allowlist de
# {entregas, calificaciones}); aca va como denylist porque academic-service es
# dueño de casi todas las tablas de la base.
#
#   entregas / calificaciones      -> modelos en evaluation-service
#                                     (tablas creadas por la migration
#                                     20260506_0001 de academic, congelada)
#   byok_keys / byok_keys_usage    -> modelo ORM propio en ai-gateway
#                                     (services/byok.py, _BYOKBase separado)
#   alembic_version_evaluation     -> tabla de tracking del alembic de evaluation
FOREIGN_OWNED_TABLES = frozenset(
    {
        "entregas",
        "calificaciones",
        "byok_keys",
        "byok_keys_usage",
        "alembic_version_evaluation",
    }
)


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Excluye del autogenerate las tablas cuyo modelo vive en otro servicio."""
    if type_ == "table":
        return name not in FOREIGN_OWNED_TABLES
    # Columnas/indices/constraints: se excluyen si cuelgan de una tabla ajena.
    table = getattr(object_, "table", None)
    if table is not None:
        return table.name not in FOREIGN_OWNED_TABLES
    return True


def get_url() -> str:
    return os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main",
    )


def run_migrations_offline() -> None:
    """Genera SQL sin conectarse (útil para dry-run en CI)."""
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
