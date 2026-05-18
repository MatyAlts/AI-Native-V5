#!/bin/bash
# Backup de las 3 bases de datos de la plataforma.
#
# Uso:
#   ./backup.sh [target_dir]
#
# Por default guarda en /var/backups/platform/{YYYY-MM-DD}/
#
# Variables de entorno (sobrescribir si hace falta):
#   PG_HOST, PG_PORT, PG_BACKUP_USER, PG_BACKUP_PASSWORD
#
# En producción corre como K8s CronJob (ver ops/k8s/backup-cronjob.yaml).
# Los backups se encriptan con age antes de subirlos a S3 glacier.

set -euo pipefail

PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_BACKUP_USER="${PG_BACKUP_USER:-backup_user}"
PG_BACKUP_PASSWORD="${PG_BACKUP_PASSWORD:?PG_BACKUP_PASSWORD es requerido}"

TARGET_DIR="${1:-/var/backups/platform/$(date +%Y-%m-%d)}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

BASES=(
  "academic_main"
  "ctr_store"
  "identity_realms"
)

mkdir -p "$TARGET_DIR"

echo "Platform backup → $TARGET_DIR (timestamp $TIMESTAMP)"
echo

export PGPASSWORD="$PG_BACKUP_PASSWORD"

for base in "${BASES[@]}"; do
  out="$TARGET_DIR/${base}-${TIMESTAMP}.sql.gz"
  echo "Dumping $base → $out"

  # --format=custom permite restore selectivo (tabla por tabla).
  # --no-owner / --no-privileges para que el restore sea portable.
  # --exclude-table-data para tablas grandes no críticas (opcional).
  pg_dump \
    --host="$PG_HOST" \
    --port="$PG_PORT" \
    --username="$PG_BACKUP_USER" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --compress=9 \
    --file="$out.tmp" \
    "$base"

  mv "$out.tmp" "$out"
  size=$(du -h "$out" | cut -f1)
  echo "  ✓ $size"
done

# Generar manifiesto con checksums para verificación post-restore
manifest="$TARGET_DIR/manifest-${TIMESTAMP}.txt"
{
  echo "Platform backup manifest"
  echo "Timestamp: $TIMESTAMP"
  echo "Host: $PG_HOST:$PG_PORT"
  echo ""
  echo "Files (SHA-256):"
  (cd "$TARGET_DIR" && sha256sum *-"${TIMESTAMP}".sql.gz)
} > "$manifest"

echo
echo "Manifiesto:"
cat "$manifest"
echo
echo "Backup completado."
