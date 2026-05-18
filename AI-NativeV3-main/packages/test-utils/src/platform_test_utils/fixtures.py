"""Fixtures reutilizables para tests de integración."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Levanta Postgres 16 con pgvector (imagen custom con extensión)."""
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Levanta Redis 7 para el bus de eventos y cache."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture
async def tenant_context(postgres_container: PostgresContainer) -> AsyncIterator[Any]:
    """Contexto con tenant_id activo seteado en la sesión.

    Usar en tests que verifican RLS:
        async def test_foo(tenant_context):
            # current_setting('app.current_tenant') ya está seteado
            ...
    """
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    tenant_id = uuid4()
    dsn = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(dsn)

    async with engine.begin() as conn:
        await conn.execute(text("SET app.current_tenant = :t"), {"t": str(tenant_id)})
        yield {"tenant_id": tenant_id, "conn": conn}

    await engine.dispose()
