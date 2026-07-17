#!/usr/bin/env python3
"""Verifica que cada tabla con tenant_id tenga RLS realmente activo y forzado.

Por cada tabla con columna tenant_id valida las TRES condiciones (ADR-001):
    1. Existe policy RLS               (pg_policies)
    2. RLS habilitado                  (pg_class.relrowsecurity = true)
    3. RLS forzado para el owner       (pg_class.relforcerowsecurity = true)

Verificar solo (1) da falsa confianza: una tabla puede tener policy con RLS
deshabilitado y la policy NUNCA se aplica.

Usar:
    python scripts/check-rls.py

Exit code:
    0 = todas las tablas con tenant_id cumplen las 3 condiciones
    1 = al menos una tabla no cumple alguna condicion (y lo lista por tabla)
    2 = no se pudo conectar a la base

Este script corre en CI como última verificación después de las migraciones.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine


async def check_database(name: str, dsn: str) -> list[str]:
    """Devuelve issues por cada tabla con tenant_id que no cumpla las 3 condiciones.

    Para cada tabla con columna ``tenant_id`` en el schema ``public`` verifica:
      1. Que exista al menos una policy RLS (``pg_policies``).
      2. Que RLS este HABILITADO (``pg_class.relrowsecurity = true``).
      3. Que RLS este FORZADO (``pg_class.relforcerowsecurity = true``),
         para que el owner de la tabla NO pueda bypassear la policy.

    Una policy sin ``relrowsecurity`` NO se aplica: la tabla queda abierta
    aunque el check viejo (que solo miraba ``pg_policies``) diera verde. Por
    eso las 3 condiciones se evaluan juntas en una sola query autoritativa
    sobre ``pg_class``.
    """
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("""
                WITH tenant_tables AS (
                    SELECT DISTINCT table_name
                    FROM information_schema.columns
                    WHERE column_name = 'tenant_id' AND table_schema = 'public'
                ),
                policy_counts AS (
                    SELECT tablename AS table_name, count(*) AS n_policies
                    FROM pg_policies
                    WHERE schemaname = 'public'
                    GROUP BY tablename
                )
                SELECT
                    t.table_name,
                    COALESCE(c.relrowsecurity, false)      AS rls_enabled,
                    COALESCE(c.relforcerowsecurity, false) AS rls_forced,
                    COALESCE(p.n_policies, 0)              AS n_policies
                FROM tenant_tables t
                LEFT JOIN pg_class c
                    ON c.relname = t.table_name
                    AND c.relkind = 'r'
                    AND c.relnamespace = 'public'::regnamespace
                LEFT JOIN policy_counts p
                    ON p.table_name = t.table_name
                ORDER BY t.table_name
            """)
            rows = list(result)
    finally:
        await engine.dispose()

    issues = []
    for table_name, rls_enabled, rls_forced, n_policies in rows:
        missing = []
        if n_policies == 0:
            missing.append("sin policy RLS (usar apply_tenant_rls)")
        if not rls_enabled:
            missing.append("RLS deshabilitado (falta ENABLE ROW LEVEL SECURITY)")
        if not rls_forced:
            missing.append("RLS sin forzar (falta FORCE ROW LEVEL SECURITY)")
        if missing:
            issues.append(f"  {name}.{table_name} -- " + "; ".join(missing))
    return issues


async def main() -> int:
    # Las 4 bases logicas separadas (ADR-003). Cada una tiene su helper
    # apply_tenant_rls definido por infrastructure/postgres/init-dbs.sql.
    databases = {
        "academic_main": os.environ.get(
            "ACADEMIC_DB_URL",
            "postgresql+asyncpg://academic_user:academic_pass@localhost:5432/academic_main",
        ),
        "ctr_store": os.environ.get(
            "CTR_DB_URL",
            "postgresql+asyncpg://ctr_user:ctr_pass@localhost:5432/ctr_store",
        ),
        "classifier_db": os.environ.get(
            "CLASSIFIER_DB_URL",
            "postgresql+asyncpg://classifier_user:classifier_pass@localhost:5432/classifier_db",
        ),
        "content_db": os.environ.get(
            "CONTENT_DB_URL",
            "postgresql+asyncpg://content_user:content_pass@localhost:5432/content_db",
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
        print("[FAIL] Tablas con tenant_id sin RLS activo+forzado:")
        for issue in all_issues:
            print(issue)
        return 1

    print("[OK] Todas las tablas con tenant_id tienen policy + RLS habilitado + FORCE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
