"""Test del aislamiento multi-tenant con RLS de Postgres.

Levanta un Postgres real con testcontainers, crea el schema desde las
migraciones, inserta datos de dos tenants y verifica que ninguno puede
ver/modificar datos del otro bajo RLS activo.

Este test es el safety-net más importante del plano académico.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration


INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE OR REPLACE FUNCTION apply_tenant_rls(table_name text)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
        table_name
    );
END;
$$ LANGUAGE plpgsql;

-- Tabla mínima para testear la policy
CREATE TABLE test_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    nombre TEXT NOT NULL
);
CREATE INDEX ON test_items (tenant_id);

-- IMPORTANTE: aplicar a un rol no-superusuario (los superusers bypasean RLS)
CREATE ROLE app_user WITH LOGIN PASSWORD 'app';
GRANT ALL ON test_items TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;

SELECT apply_tenant_rls('test_items');
"""


@pytest.fixture(scope="module")
def pg_container():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        # Bootstrap del schema
        import psycopg2

        conn = psycopg2.connect(pg.get_connection_url().replace("+psycopg2", ""))
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(INIT_SQL)
        conn.close()
        yield pg


@pytest.fixture
async def engine(pg_container):
    # Conectarse como app_user (sin privilegios de superusuario)
    base = pg_container.get_connection_url().replace("+psycopg2", "+asyncpg")
    # Extraer host/port y reemplazar user
    from urllib.parse import urlparse

    parsed = urlparse(base)
    dsn = f"postgresql+asyncpg://app_user:app@{parsed.hostname}:{parsed.port}{parsed.path}"

    engine = create_async_engine(dsn)
    yield engine
    await engine.dispose()


async def test_tenant_a_no_ve_datos_de_tenant_b(engine) -> None:
    """RLS impide que tenant A lea datos de tenant B."""
    tenant_a = uuid4()
    tenant_b = uuid4()

    # Insertar con tenant A
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        await conn.execute(
            text("INSERT INTO test_items (tenant_id, nombre) VALUES (:t, :n)"),
            {"t": tenant_a, "n": "item_de_A"},
        )

    # Insertar con tenant B
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_b)},
        )
        await conn.execute(
            text("INSERT INTO test_items (tenant_id, nombre) VALUES (:t, :n)"),
            {"t": tenant_b, "n": "item_de_B"},
        )

    # Leer con tenant A → solo ve su dato
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        result = await conn.execute(text("SELECT nombre FROM test_items ORDER BY nombre"))
        rows = [r[0] for r in result]

    assert rows == ["item_de_A"], f"Tenant A vio datos de B: {rows}"


async def test_tenant_a_no_puede_modificar_datos_de_b(engine) -> None:
    """Update desde tenant A sobre un row de tenant B no afecta nada."""
    tenant_a = uuid4()
    tenant_b = uuid4()

    # Insertar con tenant B
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_b)},
        )
        await conn.execute(
            text("INSERT INTO test_items (tenant_id, nombre) VALUES (:t, :n)"),
            {"t": tenant_b, "n": "original"},
        )

    # Intentar UPDATE masivo desde tenant A
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_a)},
        )
        result = await conn.execute(text("UPDATE test_items SET nombre = 'hacked'"))
        # rowcount debería ser 0 — RLS filtra aún el UPDATE
        assert result.rowcount == 0

    # Verificar que el dato de B no cambió
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_b)},
        )
        result = await conn.execute(
            text("SELECT nombre FROM test_items WHERE tenant_id = :t"),
            {"t": tenant_b},
        )
        assert result.scalar_one() == "original"


async def test_force_rls_aplica_a_owner(engine) -> None:
    """FORCE ROW LEVEL SECURITY aplica incluso al owner de la tabla.

    Sin FORCE, el owner bypasea RLS. Este test verifica que no.
    """
    # Acá testeamos indirectamente: app_user no es owner; el test anterior
    # ya demostró el aislamiento. Para verificar FORCE en sentido estricto,
    # el rol owner (postgres) también debería ser afectado.
    # En la migración real esto se enforza con "ALTER TABLE ... FORCE".
    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT relforcerowsecurity
                FROM pg_class
                WHERE relname = 'test_items'
            """)
        )
        assert result.scalar_one() is True, "FORCE ROW LEVEL SECURITY no activo"
