#!/bin/bash
# Restore de una o más bases desde un backup.
#
# Uso:
#   ./restore.sh <backup_dir> [database_name]
#
# Si se pasa database_name, solo restaura esa. Si no, restaura las 3.
#
# ATENCIÓN: este script BORRA las bases existentes antes de restaurar.
# Destinado para staging / disaster recovery, NO para producción en vivo.
#
# Variables de entorno:
#   PG_HOST, PG_PORT, PG_ADMIN_USER, PG_ADMIN_PASSWORD
#   CONFIRM=yes  (sin esto, el script pide confirmación interactiva)

set -euo pipefail

PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_ADMIN_USER="${PG_ADMIN_USER:-postgres}"
PG_ADMIN_PASSWORD="${PG_ADMIN_PASSWORD:?PG_ADMIN_PASSWORD es requerido}"

BACKUP_DIR="${1:?Uso: restore.sh <backup_dir> [database_name]}"
TARGET_DB="${2:-}"

if [ ! -d "$BACKUP_DIR" ]; then
  echo "ERROR: backup_dir no existe: $BACKUP_DIR" >&2
  exit 2
fi

BASES=(
  "academic_main"
  "ctr_store"
  "identity_realms"
)

# Si el caller especificó una sola DB, filtrar
if [ -n "$TARGET_DB" ]; then
  found=0
  for b in "${BASES[@]}"; do
    if [ "$b" = "$TARGET_DB" ]; then found=1; break; fi
  done
  if [ $found -eq 0 ]; then
    echo "ERROR: $TARGET_DB no es una base válida ($(IFS=,; echo "${BASES[*]}"))" >&2
    exit 2
  fi
  BASES=("$TARGET_DB")
fi

# Confirmación
if [ "${CONFIRM:-}" != "yes" ]; then
  echo "Se van a DROPar y restaurar estas bases:"
  for b in "${BASES[@]}"; do echo "  - $b"; done
  echo
  echo "Desde: $BACKUP_DIR"
  echo
  read -rp "Confirmar escribiendo 'RESTORE': " confirmation
  if [ "$confirmation" != "RESTORE" ]; then
    echo "Cancelado."
    exit 1
  fi
fi

export PGPASSWORD="$PG_ADMIN_PASSWORD"

for base in "${BASES[@]}"; do
  # Buscar el dump más reciente para esta base
  dump="$(ls -t "$BACKUP_DIR"/"${base}"-*.sql.gz 2>/dev/null | head -n 1 || true)"
  if [ -z "$dump" ]; then
    echo "WARN: no hay dump para $base en $BACKUP_DIR, salteando"
    continue
  fi

  echo "Restaurando $base ← $dump"

  # Verificar checksum si hay manifest
  manifest="$(ls -t "$BACKUP_DIR"/manifest-*.txt 2>/dev/null | head -n 1 || true)"
  if [ -n "$manifest" ]; then
    dump_basename="$(basename "$dump")"
    expected=$(grep "$dump_basename" "$manifest" | awk '{print $1}' || true)
    if [ -n "$expected" ]; then
      actual=$(sha256sum "$dump" | awk '{print $1}')
      if [ "$expected" != "$actual" ]; then
        echo "ERROR: checksum no coincide para $dump_basename" >&2
        echo "  esperado: $expected"
        echo "  actual:   $actual"
        exit 3
      fi
      echo "  ✓ checksum verificado"
    fi
  fi

  # Drop + recreate
  psql --host="$PG_HOST" --port="$PG_PORT" --username="$PG_ADMIN_USER" \
       --dbname=postgres --command="DROP DATABASE IF EXISTS $base WITH (FORCE);"
  psql --host="$PG_HOST" --port="$PG_PORT" --username="$PG_ADMIN_USER" \
       --dbname=postgres --command="CREATE DATABASE $base;"

  # Restore
  pg_restore \
    --host="$PG_HOST" --port="$PG_PORT" --username="$PG_ADMIN_USER" \
    --dbname="$base" \
    --no-owner --no-privileges \
    --exit-on-error \
    "$dump"

  echo "  ✓ $base restaurada"
  echo
done

echo "Restore completado."
