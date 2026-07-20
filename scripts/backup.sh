#!/bin/bash
# Backup completo del piloto: 4 bases Postgres + Redis (CTR streams + sessions)
# + MinIO (materiales RAG + archive CTR) + attestations Ed25519 (ADR-021).
#
# Uso:
#   ./backup.sh [target_dir]
#
# Por default guarda en /var/backups/platform/{YYYY-MM-DD}/
#
# Variables de entorno (sobrescribir si hace falta):
#   PG_HOST, PG_PORT, PG_BACKUP_USER, PG_BACKUP_PASSWORD
#   REDIS_HOST (default redis), REDIS_PORT (default 6379), REDIS_PASSWORD (opcional)
#   MINIO_HOST (default minio:9000), MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
#     MINIO_BUCKETS (CSV; default "materiales,ctr-archive")
#   ATTESTATIONS_DIR (default /var/lib/platform/attestations)
#   REMOTE_BACKUP_URL (opcional; ej "s3://bucket/path" o "b2://bucket/path") —
#     si esta definida, sube el target_dir entero a remoto con `aws s3 sync` o
#     `rclone copy`. Sin esta var, el backup queda solo en el VPS y se pierde
#     si el VPS muere (CRITICO para el piloto).
#
# Para piloto-2 (VPS UTN sin K8s) corre via systemd timer diario
# (infrastructure/systemd/platform-backup.{service,timer}). Si el deploy es
# EasyPanel-managed (sin acceso a systemd del host), correr en un container
# sidecar con cron — ver docs/VPS-DEPLOY.md seccion "Backups en EasyPanel".

set -euo pipefail

PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_BACKUP_USER="${PG_BACKUP_USER:-backup_user}"
PG_BACKUP_PASSWORD="${PG_BACKUP_PASSWORD:?PG_BACKUP_PASSWORD es requerido}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
MINIO_HOST="${MINIO_HOST:-minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"
MINIO_BUCKETS="${MINIO_BUCKETS:-materiales,ctr-archive}"
ATTESTATIONS_DIR="${ATTESTATIONS_DIR:-/var/lib/platform/attestations}"
REMOTE_BACKUP_URL="${REMOTE_BACKUP_URL:-}"

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

# ── Redis (CTR streams + sessions tutor + rate limit) ──
# RDB snapshot via BGSAVE. El stream `attestation.requests` y los sharded
# `ctr.p0..ctr.p7` viven aca; perderlos es perdida de eventos no drenados.
echo
echo "Redis BGSAVE → snapshot RDB"
redis_args=("-h" "$REDIS_HOST" "-p" "$REDIS_PORT")
if [ -n "$REDIS_PASSWORD" ]; then
  redis_args+=("-a" "$REDIS_PASSWORD" "--no-auth-warning")
fi
if redis-cli "${redis_args[@]}" BGSAVE >/dev/null 2>&1; then
  # Esperar a que BGSAVE termine (max 60s)
  for _ in $(seq 1 60); do
    state=$(redis-cli "${redis_args[@]}" LASTSAVE 2>/dev/null || echo 0)
    sleep 1
    new_state=$(redis-cli "${redis_args[@]}" LASTSAVE 2>/dev/null || echo 0)
    [ "$new_state" -gt "$state" ] && break
  done
  redis_out="$TARGET_DIR/redis-dump-${TIMESTAMP}.rdb"
  # El archivo dump.rdb vive en el container redis; lo copiamos via docker cp
  # o asumimos volume montado en /backup-source/redis si corremos en sidecar.
  if [ -n "${REDIS_DUMP_PATH:-}" ] && [ -f "$REDIS_DUMP_PATH" ]; then
    cp "$REDIS_DUMP_PATH" "$redis_out"
    gzip -9 "$redis_out"
    size=$(du -h "$redis_out.gz" | cut -f1)
    echo "  ✓ $redis_out.gz ($size)"
  else
    echo "  WARN: REDIS_DUMP_PATH no configurado o no existe — solo se disparo BGSAVE"
    echo "        Setear REDIS_DUMP_PATH=/path/to/dump.rdb (volume montado) para persistir"
  fi
else
  echo "  ERROR: redis-cli BGSAVE fallo — Redis no accesible o sin permisos"
fi

# ── MinIO (materiales RAG + archive CTR) ──
# `mc mirror` clona los buckets al target_dir. mc se autoconfigura con alias.
if [ -n "$MINIO_ACCESS_KEY" ] && [ -n "$MINIO_SECRET_KEY" ] && command -v mc >/dev/null 2>&1; then
  echo
  echo "MinIO mc mirror → buckets locales"
  mc alias set platform "http://$MINIO_HOST" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null 2>&1 || true
  IFS=',' read -ra buckets <<< "$MINIO_BUCKETS"
  minio_target="$TARGET_DIR/minio"
  mkdir -p "$minio_target"
  for bucket in "${buckets[@]}"; do
    bucket="${bucket// /}"
    [ -z "$bucket" ] && continue
    echo "  Mirroring $bucket → $minio_target/$bucket/"
    if mc mirror --quiet --overwrite "platform/$bucket" "$minio_target/$bucket/" 2>/dev/null; then
      size=$(du -sh "$minio_target/$bucket" 2>/dev/null | cut -f1)
      echo "    ✓ $size"
    else
      echo "    WARN: bucket $bucket no existe o sin permisos"
    fi
  done
  # Tarball para reducir count de objetos al subir a remoto
  if [ -d "$minio_target" ] && [ "$(ls -A "$minio_target" 2>/dev/null)" ]; then
    minio_archive="$TARGET_DIR/minio-${TIMESTAMP}.tar.gz"
    tar -czf "$minio_archive" -C "$TARGET_DIR" minio
    rm -rf "$minio_target"
    size=$(du -h "$minio_archive" | cut -f1)
    echo "  ✓ $minio_archive ($size)"
  fi
else
  echo
  echo "WARN: MinIO backup salteado (faltan MINIO_ACCESS_KEY/SECRET_KEY o no hay 'mc' en PATH)"
fi

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

# ── Upload off-site (CRITICO para sobrevivir muerte del VPS) ──
# Sin este paso, los backups viven en el mismo VPS que la prod — un crash o
# delete accidental se lleva todo. Soporta S3 (aws-cli) y B2/otros via rclone.
if [ -n "$REMOTE_BACKUP_URL" ]; then
  echo "Sincronizando a $REMOTE_BACKUP_URL …"
  case "$REMOTE_BACKUP_URL" in
    s3://*)
      if command -v aws >/dev/null 2>&1; then
        aws s3 sync "$TARGET_DIR/" "$REMOTE_BACKUP_URL/$(basename "$TARGET_DIR")/" --quiet
        echo "  ✓ Subido via aws s3 sync"
      else
        echo "  ERROR: aws-cli no instalado para destino s3://"
      fi
      ;;
    b2://*|gs://*|azure://*|rclone:*)
      if command -v rclone >/dev/null 2>&1; then
        # rclone usa su propia sintaxis: remote:bucket/path
        rclone_dest="${REMOTE_BACKUP_URL#rclone:}"
        rclone copy "$TARGET_DIR/" "$rclone_dest/$(basename "$TARGET_DIR")/" --quiet
        echo "  ✓ Subido via rclone"
      else
        echo "  ERROR: rclone no instalado para destino remoto"
      fi
      ;;
    *)
      echo "  ERROR: protocolo no soportado en REMOTE_BACKUP_URL ($REMOTE_BACKUP_URL)"
      echo "        Usar s3://, b2://, gs://, azure://, o rclone:remote-name"
      ;;
  esac
else
  echo "WARN: REMOTE_BACKUP_URL no seteada — backup queda SOLO en el VPS."
  echo "      Si el VPS se cae, perdes todo. Configurar upload off-site."
fi

echo
echo "Backup completado."
