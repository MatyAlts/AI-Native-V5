#!/usr/bin/env python3
"""Verifica que cada tabla con tenant_id tenga política RLS activa.

Usar:
    python scripts/check-rls.py

Exit code:
    0 = todas las tablas con tenant_id tienen policy
    1 = al menos una tabla con tenant_id NO tiene policy (y lo lista)
    2 = no se pudo conectar a la base

Este script corre en CI como última verificación después de las migraciones.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine


async def check_database(name: str, dsn: str) -> list[str]:
    """Devuelve la lista de tablas con tenant_id sin policy RLS."""
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("""
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
            tables_without_rls = [row[0] for row in result]

            # Verificar también FORCE RLS
            result = await conn.exec_driver_sql("""
                SELECT relname FROM pg_class c
                JOIN information_schema.columns col
                    ON col.table_name = c.relname AND col.column_name = 'tenant_id'
                WHERE col.table_schema = 'public'
                  AND c.relkind = 'r'
                  AND c.relrowsecurity = true
                  AND c.relforcerowsecurity = false
            """)
            tables_without_force = [row[0] for row in result]
    finally:
        await engine.dispose()

    issues = []
    for t in tables_without_rls:
        issues.append(f"  {name}.{t} -- sin politica RLS (usar apply_tenant_rls)")
    for t in tables_without_force:
        issues.append(f"  {name}.{t} -- sin FORCE ROW LEVEL SECURITY")
    return issues


async def main() -> int:
    databases = {
        "academic_main": os.environ.get(
            "ACADEMIC_DB_URL",
            "postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main",
        ),
        "ctr_store": os.environ.get(
            "CTR_DB_URL",
            "postgresql+asyncpg://ctr_user:ctr_pass@localhost:5432/ctr_store",
        ),
    }

    all_issues: list[str] = []
    for name, dsn in databases.items():
        try:
            issues = await check_database(name, dsn)
            all_issues.extend(issues)
        except Exception as e:
            print(f"ERROR conectando a {name}: {e}", file=sys.stderr)
            return 2

    if all_issues:
        print("[FAIL] Tablas con tenant_id sin policy RLS:")
        for issue in all_issues:
            print(issue)
        return 1

    print("[OK] Todas las tablas con tenant_id tienen policy RLS + FORCE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
