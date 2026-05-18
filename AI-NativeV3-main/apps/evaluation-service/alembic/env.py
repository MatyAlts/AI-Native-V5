"""Alembic environment para evaluation-service.

Notas importantes:

1. evaluation-service comparte la DB ``academic_main`` con academic-service
   (verdad permanente del piloto, ver CLAUDE.md). Por eso la URL se toma de
   ``ACADEMIC_DB_URL`` (misma var que usa el migrate-all.sh).

2. Como dos servicios apuntan a la MISMA base, NO podemos usar la tabla
   ``alembic_version`` por defecto — colisionarian las heads. Configuramos
   ``version_table='alembic_version_evaluation'`` para mantener namespaces
   independientes en la misma DB.

3. ``include_object`` filtra el autogenerate para que solo "vea" las tablas
   propias de evaluation-service (entregas, calificaciones). Sin este filtro,
   ``alembic revision --autogenerate`` propondria droppear todas las tablas
   de academic (que NO estan en el metadata de evaluation).
"""

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

from evaluation_service.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tablas owned por evaluation-service. Todo lo que no este aca se ignora
# en autogenerate (las crea/maneja academic-service en su propio alembic).
EVALUATION_OWNED_TABLES = frozenset({"entregas", "calificaciones"})


def get_url() -> str:
    # Comparte ACADEMIC_DB_URL — academic-service y evaluation-service viven
    # en la misma DB academic_main (ver CLAUDE.md "Cuatro bases logicas").
    return os.environ.get(
        "ACADEMIC_DB_URL",
        "postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main",
    )


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Filtra autogenerate a tablas owned por evaluation-service."""
    if type_ == "table":
        return name in EVALUATION_OWNED_TABLES
    # Para columnas/indices/constraints: solo si pertenecen a tabla owned.
    if hasattr(object_, "table") and object_.table is not None:
        return object_.table.name in EVALUATION_OWNED_TABLES
    return True


def run_migrations_offline() -> None:
    """Genera SQL sin conectarse (util para dry-run en CI)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version_evaluation",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version_evaluation",
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
