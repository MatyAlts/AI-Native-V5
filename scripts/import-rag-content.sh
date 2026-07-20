#!/usr/bin/env bash
# Importa el contenido del RAG (materiales + chunks con embeddings) en el
# VPS. El dump viene de scripts/export-rag-content.sh ejecutado en local.
#
# IMPORTANTE — re-mapeo de UUIDs
# ------------------------------
# El dump del local trae tenant_id y materia_id origen. En el VPS quizas
# uses otros (ej. seed-utn-vps.py crea tenant d0d0d0d0-* y materia
# d0d0d0d0-aa01-*). Para que el RAG funcione, tenant_id y materia_id del
# material deben matchear con los del CALLER (alumno/docente) al hacer
# queries. Sin --target-tenant / --target-materia, importa con los UUIDs
# originales (util si ya alineaste los seeds).
#
# DESTRUCTIVO: TRUNCATE de las tablas `materiales` y `chunks` del
# content_db antes de cargar. Asume content_db recien deployado o sin
# data importante que conservar. Para merge incremental hace falta otra
# estrategia (no implementada — usar el UI de /materiales para uploads
# incrementales).
#
# Uso:
#   bash scripts/import-rag-content.sh \
#     --dump infrastructure/exports/rag-content-YYYYMMDD-HHMMSS.tar.gz \
#     [--target-tenant <UUID>] \
#     [--target-materia <UUID>] \
#     [--target-comision <UUID>]
#
# Variables env opcionales: PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, CONTENT_DB_NAME.

set -euo pipefail

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
CONTENT_DB_NAME="${CONTENT_DB_NAME:-content_db}"

DUMP_PATH=""
TARGET_TENANT=""
TARGET_MATERIA=""
TARGET_COMISION=""
ASSUME_YES="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump) DUMP_PATH="$2"; shift 2 ;;
    --target-tenant) TARGET_TENANT="$2"; shift 2 ;;
    --target-materia) TARGET_MATERIA="$2"; shift 2 ;;
    --target-comision) TARGET_COMISION="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES="true"; shift ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Arg desconocido: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$DUMP_PATH" ]]; then
  echo "Uso: $0 --dump <archivo.tar.gz> [--target-tenant UUID --target-materia UUID --target-comision UUID]" >&2
  exit 2
fi

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "[import-rag] ERROR: archivo no existe: $DUMP_PATH" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

export PGPASSWORD="$PG_PASSWORD"

echo "[import-rag] target DB:    $PG_USER@$PG_HOST:$PG_PORT/$CONTENT_DB_NAME"
echo "[import-rag] dump:         $DUMP_PATH ($(stat -c%s "$DUMP_PATH" | numfmt --to=iec))"
echo "[import-rag] target tenant: ${TARGET_TENANT:-<sin remap>}"
echo "[import-rag] target materia:${TARGET_MATERIA:-<sin remap>}"
echo "[import-rag] target comision:${TARGET_COMISION:-<sin remap>}"
echo ""

# Pre-flight: chequear estado actual
echo "[import-rag] estado actual del content_db:"
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -t -c "
SELECT 'materiales=' || count(*) FROM materiales WHERE deleted_at IS NULL
UNION ALL SELECT 'chunks=' || count(*) FROM chunks;
" 2>&1 | grep -v '^$' | tr -d ' '
echo ""

if [[ "$ASSUME_YES" != "true" ]]; then
  read -p "Esto hara TRUNCATE de materiales y chunks. Continuar? [y/N] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "[import-rag] cancelado"
    exit 0
  fi
fi

# Extraer dump
TMP_DIR=$(mktemp -d /tmp/rag-import.XXXXXX)
trap 'rm -rf "$TMP_DIR"' EXIT

tar xzf "$DUMP_PATH" -C "$TMP_DIR"
SQL_FILE="$TMP_DIR/content_db.sql"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "[import-rag] ERROR: el tarball no contiene content_db.sql" >&2
  exit 1
fi

echo "[import-rag] MANIFEST.txt:"
[[ -f "$TMP_DIR/MANIFEST.txt" ]] && sed 's/^/  /' "$TMP_DIR/MANIFEST.txt"
echo ""

# TRUNCATE destino
echo "[import-rag] TRUNCATE chunks + materiales..."
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -c "
TRUNCATE chunks CASCADE;
TRUNCATE materiales CASCADE;
" 2>&1 | tail -3

# Cargar el SQL tal cual (sin sed, evitamos cascadeos)
echo "[import-rag] cargando dump en content_db..."
docker exec -i platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -v ON_ERROR_STOP=1 \
  < "$SQL_FILE" \
  2>&1 | tail -5

# Re-mapeos en SQL (atomico, sin posibilidad de cascade)
UPDATE_PARTS=()
if [[ -n "$TARGET_TENANT" ]]; then
  UPDATE_PARTS+=("tenant_id = '$TARGET_TENANT'")
fi
if [[ -n "$TARGET_MATERIA" ]]; then
  UPDATE_PARTS+=("materia_id = '$TARGET_MATERIA'")
fi
if [[ -n "$TARGET_COMISION" ]]; then
  UPDATE_PARTS+=("comision_id = '$TARGET_COMISION'")
fi

if [[ ${#UPDATE_PARTS[@]} -gt 0 ]]; then
  SET_CLAUSE=$(IFS=,; echo "${UPDATE_PARTS[*]}")
  echo ""
  echo "[import-rag] re-mapeo SQL: SET $SET_CLAUSE"
  docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -c "
    UPDATE materiales SET $SET_CLAUSE WHERE deleted_at IS NULL;
    UPDATE chunks     SET $SET_CLAUSE;
  " 2>&1 | tail -5
fi

# Verificacion final
echo ""
echo "[import-rag] estado final del content_db:"
docker exec platform-postgres psql -U "$PG_USER" -d "$CONTENT_DB_NAME" -t -c "
SELECT 'materiales=' || count(*) FROM materiales WHERE deleted_at IS NULL
UNION ALL SELECT 'chunks=' || count(*) FROM chunks
UNION ALL SELECT 'tenants_distintos=' || count(DISTINCT tenant_id) FROM materiales WHERE deleted_at IS NULL
UNION ALL SELECT 'materia_id_final=' || (SELECT DISTINCT materia_id FROM materiales WHERE deleted_at IS NULL LIMIT 1);
" 2>&1 | grep -v '^$' | tr -d ' '

echo ""
echo "[import-rag] OK"
echo ""
echo "Verificar end-to-end con:"
echo "  curl http://127.0.0.1:8009/api/v1/content/retrieve \\"
echo "    -H 'X-Tenant-Id: ${TARGET_TENANT:-<tenant>}' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"materia_id\":\"${TARGET_MATERIA:-<materia>}\",\"query\":\"variables python\",\"k\":3}'"
