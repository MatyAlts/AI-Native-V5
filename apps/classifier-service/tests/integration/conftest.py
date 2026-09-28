"""Fixtures compartidas para tests de integración contra Postgres real
(`classifier_db` del contenedor de desarrollo local `platform-postgres`).

Ningún test de este directorio commitea: cada uno abre su propia sesión con
un `tenant_id` aleatorio, corre dentro de una única transacción y hace
`rollback()` al final — nunca `commit()`. No se persiste nada.
"""

from __future__ import annotations

import socket
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DB_URL = "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:5432/classifier_db"


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="platform-postgres no está corriendo en 127.0.0.1:5432",
)


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        try:
            yield session, tenant_id
        finally:
            await session.rollback()
    await engine.dispose()
