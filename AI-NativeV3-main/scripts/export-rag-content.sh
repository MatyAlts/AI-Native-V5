#!/usr/bin/env bash
# Exporta el contenido del RAG (tabla `materiales` + `chunks` con embeddings
# de pgvector) del content_db local a un archivo tar.gz portable. Pensado
# para llevarse al VPS y restaurarlo con import-rag-content.sh.
#
# Lo que SE exporta:
#   - materiales: metadatos (nombre, tipo, chunks_count, content_hash, etc)
#   - chunks: contenido textual + embedding vector(1024) + posicion
#
# Lo que NO se exporta:
#   - Archivos binarios originales del MinIO/storage (en dev local con
#     STORAGE=mock no existen; en prod con MinIO real se exportarian con
#     `mc mirror`).
#
# Uso:
#   bash scripts/export-rag-content.sh
#   bash scripts/export-rag-content.sh --output /tmp/rag-utn-2026-05-22.tar.gz
#
# Variables env opcionales:
#   PG_HOST          (default: localhost)
#   PG_PORT          (default: 5432)
#   PG_USER          (default: postgres)
#   PG_PASSWORD      (default: postgres)
#   CONTENT_DB_NAME  (default: content_db)

set -euo pipefail

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
CONTENT_DB_NAME="${CONTENT_DB_NAME:-content_db}"

OUTPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Arg desconocido: $1" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

if [[ -z "$OUTPUT" ]]; then
  ts=$(date -u +%Y%m%d-%H%M%S)
  mkdir -p "$REPO_ROOT/infrastructure/exports"
  OUTPUT="$REPO_ROOT/infrastructure/exports/rag-content-${ts}.tar.gz"
fi

export PGPASSWORD="$PG_PASSWORD"

echo "[export-rag] target DB: $PG_USER@$PG_HOST:$PG_PORT/$CONTENT_DB_NAME"
echo "[export-rag] output:    $OUTPUT"
echo ""

# Stats pre-export
echo "[export-rag] inventario:"
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -t -c "
SELECT
  (SELECT count(*) FROM materiales WHERE deleted_at IS NULL) AS materiales_activos,
  (SELECT count(*) FROM chunks)                              AS chunks_total,
  (SELECT count(DISTINCT tenant_id) FROM materiales WHERE deleted_at IS NULL) AS tenants_distintos,
  (SELECT count(DISTINCT materia_id) FROM materiales WHERE deleted_at IS NULL AND materia_id IS NOT NULL) AS materias_distintas;
" 2>&1 | tr -s ' '

echo ""
echo "[export-rag] tenant_id(s) presentes:"
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -t -c "
SELECT DISTINCT tenant_id FROM materiales WHERE deleted_at IS NULL;
" 2>&1 | grep -v '^$' | tr -d ' '

echo ""
echo "[export-rag] materia_id(s) presentes:"
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -t -c "
SELECT DISTINCT materia_id FROM materiales WHERE deleted_at IS NULL AND materia_id IS NOT NULL;
" 2>&1 | grep -v '^$' | tr -d ' '

echo ""
echo "[export-rag] generando pg_dump (data-only)..."

TMP_SQL=$(mktemp /tmp/rag-content.XXXXXX.sql)
trap 'rm -f "$TMP_SQL"' EXIT

# --column-inserts: genera INSERT statements en lugar de COPY (mas grande pero
# postprocesable con sed para re-mapeo de UUIDs).
# --data-only: solo datos, no schema (el schema lo crea Alembic en el VPS).
# --disable-triggers: para que INSERT no falle por FK durante restore.
docker exec platform-postgres pg_dump \
  -U "$PG_USER" \
  -d "$CONTENT_DB_NAME" \
  --data-only \
  --column-inserts \
  --disable-triggers \
  --no-owner \
  --no-privileges \
  --table=materiales \
  --table=chunks \
  > "$TMP_SQL"

rows=$(wc -l < "$TMP_SQL")
sql_size_kb=$(( $(stat -c%s "$TMP_SQL") / 1024 ))
echo "[export-rag] dump: ${rows} lineas, ${sql_size_kb} KB"

# Empaquetar con metadata
TMP_DIR=$(mktemp -d /tmp/rag-content-pkg.XXXXXX)
trap 'rm -rf "$TMP_DIR" "$TMP_SQL"' EXIT

cp "$TMP_SQL" "$TMP_DIR/content_db.sql"
cat > "$TMP_DIR/MANIFEST.txt" <<EOF
RAG content export — generado por scripts/export-rag-content.sh
Fecha:    $(date -u +%Y-%m-%dT%H:%M:%SZ)
Origen:   $PG_USER@$PG_HOST:$PG_PORT/$CONTENT_DB_NAME
Tamaño:   ${sql_size_kb} KB (SQL plain)

Restaurar con:
  bash scripts/import-rag-content.sh --dump <este-archivo>.tar.gz [...opts]

Tenants y materias en el dump: ver header del SQL.
EOF

tar czf "$OUTPUT" -C "$TMP_DIR" content_db.sql MANIFEST.txt

final_size_kb=$(( $(stat -c%s "$OUTPUT") / 1024 ))
echo ""
echo "[export-rag] OK"
echo "[export-rag] archivo: $OUTPUT (${final_size_kb} KB)"
echo ""
echo "Para llevar al VPS:"
echo "  scp $OUTPUT platform@<vps-host>:/opt/platform/platform/AI-NativeV3-main/infrastructure/exports/"
echo ""
echo "Despues, en el VPS:"
echo "  bash scripts/import-rag-content.sh \\"
echo "    --dump infrastructure/exports/$(basename $OUTPUT) \\"
echo "    --target-tenant <NUEVO_TENANT_UUID> \\"
echo "    --target-materia <NUEVA_MATERIA_UUID>"
