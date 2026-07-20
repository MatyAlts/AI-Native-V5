#!/usr/bin/env bash
# setup-rls-test-user.sh
# Crea (idempotentemente) el rol `app_runtime` non-superuser/NOBYPASSRLS
# en Postgres, y le otorga los permisos minimos para correr los tests
# de aislamiento multi-tenant en `packages/platform-ops/tests/test_rls_postgres.py`.
#
# Por que existe este script:
#   - Postgres bypassa RLS para roles superuser (postgres) o roles con BYPASSRLS.
#   - Si `make test-rls` corre como `postgres`, FORCE ROW SECURITY se ignora y
#     los tests pasan en silencio sin verificar nada (CI miente).
#   - Este script materializa el `CTR_STORE_URL_FOR_RLS_TESTS` documentado en
#     CLAUDE.md ("apuntando a una base con usuario no-superuser para que RLS aplique").
#
# Output: un rol `app_runtime` con login + GRANT en las 4 bases logicas + hooks
# para tablas futuras via ALTER DEFAULT PRIVILEGES.

set -euo pipefail

PSQL="docker exec platform-postgres psql -U postgres"
ROLE_NAME="${RLS_TEST_ROLE:-app_runtime}"
ROLE_PASS="${RLS_TEST_PASSWORD:-app_runtime}"

echo "================================================================"
echo "  Setup de usuario test RLS: $ROLE_NAME"
echo "================================================================"

# ---------------------------------------------------------------------------
# 1. Crear el rol app_runtime (idempotente)
#    - LOGIN: necesario para que el driver asyncpg autentique.
#    - NOSUPERUSER + NOBYPASSRLS: explicito, defensa en profundidad ante
#      defaults que cambien entre versiones de Postgres.
# ---------------------------------------------------------------------------
echo ""
echo "[1/3] Creando rol $ROLE_NAME (si no existe)..."
$PSQL -c "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$ROLE_NAME') THEN
    CREATE ROLE $ROLE_NAME WITH LOGIN PASSWORD '$ROLE_PASS' NOSUPERUSER NOBYPASSRLS;
    RAISE NOTICE 'Rol $ROLE_NAME creado';
  ELSE
    -- Si ya existe, asegurar que el password matchea y que no tiene bypass
    ALTER ROLE $ROLE_NAME WITH LOGIN PASSWORD '$ROLE_PASS' NOSUPERUSER NOBYPASSRLS;
    RAISE NOTICE 'Rol $ROLE_NAME ya existia, atributos sincronizados';
  END IF;
END \$\$;"

# ---------------------------------------------------------------------------
# 2. Verificacion explicita: NOSUPERUSER + NOBYPASSRLS
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Verificando atributos del rol..."
ATTRS=$($PSQL -tAc "SELECT (rolsuper::int)::text || '|' || (rolbypassrls::int)::text FROM pg_roles WHERE rolname = '$ROLE_NAME';" | tr -d '[:space:]')
if [ "$ATTRS" != "0|0" ]; then
  echo "  ERROR: $ROLE_NAME tiene atributos invalidos: rolsuper|rolbypassrls = $ATTRS"
  echo "         Esperado: 0|0 (ningun bypass)"
  exit 1
fi
echo "  OK: $ROLE_NAME es NOSUPERUSER y NOBYPASSRLS"

# ---------------------------------------------------------------------------
# 3. Otorgar permisos en las 4 bases logicas
#    GRANT minimo:
#      - USAGE en schema public (sin esto, ni siquiera ve las tablas)
#      - SELECT/INSERT/UPDATE/DELETE en todas las tablas existentes
#      - USAGE/SELECT/UPDATE en sequences (autoincrement)
#      - ALTER DEFAULT PRIVILEGES para tablas/sequences futuras (cuando
#        alembic crea tablas nuevas, no hay que volver a correr este script)
# ---------------------------------------------------------------------------
grant_db() {
  local db="$1"
  echo "  DB: $db"
  $PSQL -d "$db" -c "GRANT USAGE ON SCHEMA public TO $ROLE_NAME;"
  $PSQL -d "$db" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $ROLE_NAME;"
  $PSQL -d "$db" -c "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO $ROLE_NAME;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $ROLE_NAME;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO $ROLE_NAME;"
}

echo ""
echo "[3/3] Otorgando permisos en las 4 bases..."
for db in academic_main ctr_store classifier_db content_db; do
  if $PSQL -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1; then
    grant_db "$db"
  else
    echo "  SKIP: $db no existe (corre 'make migrate' primero si la necesitas)"
  fi
done

# ---------------------------------------------------------------------------
# 4. Limpieza de policies legacy duplicadas en ctr_store
#    Contexto: ambientes pre-migration tienen un policy `tenant_isolation`
#    (sin sufijo) creada manualmente o por una migration descartada. Hace
#    `current_setting('app.current_tenant', true)::uuid` que ROMPE cuando el
#    GUC esta vacio (default fail-safe). La migration 20260721_0002 creo la
#    version correcta con sufijo `_<table>` y comparacion texto-a-texto.
#    Las policies se OR-ean: la legacy explota ANTES de que la nueva pueda
#    matchear. Drop idempotente solo de las legacy si existen.
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Limpiando policies legacy duplicadas en ctr_store..."
for table in episodes events dead_letters; do
  exists=$($PSQL -d ctr_store -tAc "SELECT 1 FROM pg_policy WHERE polname = 'tenant_isolation' AND polrelid = '$table'::regclass" 2>/dev/null || echo "")
  if [ -n "$exists" ]; then
    echo "  DROP POLICY tenant_isolation ON $table (legacy con uuid-cast inseguro)"
    $PSQL -d ctr_store -c "DROP POLICY IF EXISTS tenant_isolation ON $table"
  fi
done

echo ""
echo "================================================================"
echo "  $ROLE_NAME listo para tests RLS"
echo "================================================================"
echo ""
echo "URL para tests:"
echo "  CTR_STORE_URL_FOR_RLS_TESTS=postgresql+asyncpg://$ROLE_NAME:$ROLE_PASS@localhost:5432/ctr_store"
echo ""
echo "Correr suite:"
echo "  make test-rls"
echo ""
