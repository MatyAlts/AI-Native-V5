"""Helpers para verificar que RLS esté bien configurado.

Estos helpers se usan tanto en tests como en el script check-rls.py
que corre en CI contra la base de staging.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def list_tables_with_tenant_id(conn: AsyncConnection) -> list[str]:
    """Lista todas las tablas que tienen columna tenant_id."""
    result = await conn.execute(
        text("""
            SELECT DISTINCT table_name
            FROM information_schema.columns
            WHERE column_name = 'tenant_id'
              AND table_schema = 'public'
            ORDER BY table_name
        """)
    )
    return [row[0] for row in result]


async def list_tables_without_rls_policy(conn: AsyncConnection) -> list[str]:
    """Lista tablas con tenant_id pero sin política RLS activa.

    Esta función es el core del safety check: si una tabla tiene tenant_id
    pero no tiene policy, hay riesgo de filtrar datos cruzados.
    """
    result = await conn.execute(
        text("""
            WITH tenant_tables AS (
                SELECT DISTINCT table_name
                FROM information_schema.columns
                WHERE column_name = 'tenant_id' AND table_schema = 'public'
            ),
            rls_tables AS (
                SELECT DISTINCT tablename AS table_name
                FROM pg_policies
                WHERE schemaname = 'public'
            )
            SELECT t.table_name FROM tenant_tables t
            LEFT JOIN rls_tables r ON t.table_name = r.table_name
            WHERE r.table_name IS NULL
            ORDER BY t.table_name
        """)
    )
    return [row[0] for row in result]


async def assert_rls_enabled(conn: AsyncConnection) -> None:
    """Assertion usable en tests: falla si alguna tabla con tenant_id no tiene policy."""
    tables_without_rls = await list_tables_without_rls_policy(conn)
    if tables_without_rls:
        raise AssertionError(
            f"Tablas con tenant_id pero sin política RLS: {tables_without_rls}. "
            "Usar apply_tenant_rls() en la migración correspondiente."
        )


async def assert_table_has_force_rls(conn: AsyncConnection, table: str) -> None:
    """Verifica que FORCE ROW LEVEL SECURITY esté activo (aplica incluso a superusuarios).

    Sin FORCE, un bug que se conecte con rol superusuario bypasea RLS.
    """
    result = await conn.execute(
        text("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname = :t AND relnamespace = 'public'::regnamespace
        """),
        {"t": table},
    )
    row = result.one_or_none()
    if row is None:
        raise AssertionError(f"Tabla {table} no existe")
    if not row[0]:
        raise AssertionError(f"Tabla {table} no tiene RLS habilitado")
    if not row[1]:
        raise AssertionError(f"Tabla {table} no tiene FORCE ROW LEVEL SECURITY")
