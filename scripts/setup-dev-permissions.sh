#!/usr/bin/env bash
# setup-dev-permissions.sh
# Post-migration setup: grants DB permissions to service users and configures
# the app.current_tenant GUC on all 4 databases.
# Safe to re-run (idempotent).

set -euo pipefail

PSQL="docker exec platform-postgres psql -U postgres"

echo "================================================================"
echo "  Setup de permisos de base de datos (post-migración)"
echo "================================================================"

# ---------------------------------------------------------------------------
# 1. Crear el rol platform_app si no existe
# ---------------------------------------------------------------------------
echo ""
echo "[1/6] Creando rol platform_app (si no existe)..."
$PSQL -c "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'platform_app') THEN
    CREATE ROLE platform_app NOLOGIN;
    RAISE NOTICE 'Rol platform_app creado';
  ELSE
    RAISE NOTICE 'Rol platform_app ya existe';
  END IF;
END \$\$;"

# ---------------------------------------------------------------------------
# Helper: grant permisos a un usuario de servicio + platform_app en una DB
# ---------------------------------------------------------------------------
grant_db() {
  local db="$1"
  local svc_user="$2"

  echo ""
  echo "  DB: $db  →  usuario: $svc_user"

  # Asegurarse de que el usuario de servicio existe (idempotente)
  $PSQL -c "DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$svc_user') THEN
      CREATE ROLE $svc_user WITH LOGIN PASSWORD '$svc_user';
      RAISE NOTICE 'Usuario $svc_user creado';
    ELSE
      RAISE NOTICE 'Usuario $svc_user ya existe';
    END IF;
  END \$\$;"

  # Permisos de servicio
  $PSQL -d "$db" -c "GRANT USAGE ON SCHEMA public TO $svc_user;"
  $PSQL -d "$db" -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO $svc_user;"
  $PSQL -d "$db" -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO $svc_user;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $svc_user;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $svc_user;"

  # Permisos de platform_app
  $PSQL -d "$db" -c "GRANT USAGE ON SCHEMA public TO platform_app;"
  $PSQL -d "$db" -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO platform_app;"
  $PSQL -d "$db" -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO platform_app;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO platform_app;"
  $PSQL -d "$db" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO platform_app;"

  # GUC para RLS: app.current_tenant disponible sin SET explícito
  $PSQL -c "ALTER DATABASE $db SET app.current_tenant = '';"

  echo "  OK: $db"
}

# ---------------------------------------------------------------------------
# 2-5. Cada base de datos
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] academic_main → academic_user"
grant_db "academic_main" "academic_user"

echo ""
echo "[3/6] ctr_store → ctr_user"
grant_db "ctr_store" "ctr_user"

echo ""
echo "[4/6] classifier_db → classifier_user"
grant_db "classifier_db" "classifier_user"

echo ""
echo "[5/6] content_db → content_user"
grant_db "content_db" "content_user"

# ---------------------------------------------------------------------------
# 6. Verificación rápida
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Verificación: GUC app.current_tenant en cada base..."
for db in academic_main ctr_store classifier_db content_db; do
  result=$($PSQL -d "$db" -tAc "SHOW app.current_tenant;" 2>&1 || true)
  echo "  $db: app.current_tenant='$result'"
done

echo ""
echo "================================================================"
echo "  Permisos configurados correctamente"
echo "================================================================"
echo ""
echo "Recordatorio: los servicios deben llamar"
echo "  SET LOCAL app.current_tenant = '<tenant_id>'"
echo "al inicio de cada request para que RLS aplique."
echo ""
