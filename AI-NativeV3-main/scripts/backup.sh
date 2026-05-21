#!/bin/bash
# Backup de las 4 bases de datos de la plataforma (ADR-003) + attestations Ed25519.
#
# Uso:
#   ./backup.sh [target_dir]
#
# Por default guarda en /var/backups/platform/{YYYY-MM-DD}/
#
# Variables de entorno (sobrescribir si hace falta):
#   PG_HOST, PG_PORT, PG_BACKUP_USER, PG_BACKUP_PASSWORD
#   ATTESTATIONS_DIR (default /var/lib/platform/attestations) — directorio con
#                    los archivos attestations-YYYY-MM-DD.jsonl firmados con Ed25519
#                    (evidencia criptografica de la tesis, ADR-021).
#
# Para piloto-2 (VPS UTN sin K8s) corre via systemd timer diario.
# Ver infrastructure/systemd/platform-backup.{service,timer} y docs/VPS-DEPLOY.md.

set -euo pipefail

PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_BACKUP_USER="${PG_BACKUP_USER:-backup_user}"
PG_BACKUP_PASSWORD="${PG_BACKUP_PASSWORD:?PG_BACKUP_PASSWORD es requerido}"
ATTESTATIONS_DIR="${ATTESTATIONS_DIR:-/var/lib/platform/attestations}"

TARGET_DIR="${1:-/var/backups/platform/$(date +%Y-%m-%d)}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

# Las 4 bases logicas separadas (ADR-003). content_db agregada en 2026-05-19
# (estaba ausente — gap detectado en auditoria pre-prod, materiales del piloto
# vivian en content_db sin estrategia de backup). identity_realms removida
# (ADR-041: identity-service deprecated, auth movida a api-gateway).
BASES=(
  "academic_main"
  "ctr_store"
  "classifier_db"
  "content_db"
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

# ── Attestations Ed25519 (evidencia criptografica del piloto, ADR-021) ──
# Estos JSONL son la cadena de custodia firmada por integrity-attestation-service.
# Perderlos invalida la cadena criptografica del piloto — son insustituibles.
if [ -d "$ATTESTATIONS_DIR" ]; then
  attestations_archive="$TARGET_DIR/attestations-${TIMESTAMP}.tar.gz"
  echo
  echo "Archivando attestations Ed25519 desde $ATTESTATIONS_DIR"
  files=$(cd "$ATTESTATIONS_DIR" && ls -1 attestations-*.jsonl 2>/dev/null || true)
  if [ -n "$files" ]; then
    tar -czf "$attestations_archive" -C "$ATTESTATIONS_DIR" $files
    size=$(du -h "$attestations_archive" | cut -f1)
    echo "  ✓ $attestations_archive ($size)"
  else
    echo "  WARN: no se encontraron archivos attestations-*.jsonl"
    echo "        Si es el primer dia del piloto-2 es normal. Si no, investigar urgente."
  fi
else
  echo
  echo "WARN: ATTESTATIONS_DIR no existe ($ATTESTATIONS_DIR) — saltando backup de attestations"
fi

# Generar manifiesto con checksums para verificación post-restore
manifest="$TARGET_DIR/manifest-${TIMESTAMP}.txt"
{
  echo "Platform backup manifest"
  echo "Timestamp: $TIMESTAMP"
  echo "Host: $PG_HOST:$PG_PORT"
  echo "Attestations source: $ATTESTATIONS_DIR"
  echo ""
  echo "Files (SHA-256):"
  (cd "$TARGET_DIR" && sha256sum *-"${TIMESTAMP}".sql.gz 2>/dev/null || true)
  (cd "$TARGET_DIR" && sha256sum attestations-"${TIMESTAMP}".tar.gz 2>/dev/null || true)
} > "$manifest"

echo
echo "Manifiesto:"
cat "$manifest"
echo
echo "Backup completado."
