#!/bin/bash
# Orquesta alembic upgrade head de los 4 servicios con DB.
#
# Uso:
#   ./scripts/migrate-all.sh [--dry-run]
#
# Variables de entorno requeridas (usar usuario postgres superuser — las
# migraciones ejecutan CREATE ROLE, ALTER DATABASE y operaciones RLS que
# requieren privilegios de superusuario):
#   ACADEMIC_DB_URL       — postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main
#   CTR_DB_URL         — postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store
#   CLASSIFIER_DB_URL     — postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db
#   CONTENT_DB_URL        — postgresql+asyncpg://postgres:postgres@localhost:5432/content_db
#
# Cada env var es leída directamente por el alembic/env.py del servicio
# correspondiente. El script exporta la var correcta antes de invocar alembic.
#
# Orden:
#   1. academic-service (tiene users/comisiones — referenciado por los otros)
#   2. ctr-service (episodes + events criptográficos)
#   3. classifier-service (classifications)
#   4. content-service (materials + chunks RAG)
#
# Con --dry-run muestra los comandos sin ejecutar. Usar primero en
# staging para detectar problemas de config antes de prod.

set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

_require_env() {
  local var="$1"
  if [ -z "${!var:-}" ]; then
    echo "ERROR: variable $var no seteada" >&2
    exit 3
  fi
}

_require_env CTR_DB_URL
_require_env ACADEMIC_DB_URL
_require_env CLASSIFIER_DB_URL
_require_env CONTENT_DB_URL

run_migration() {
  local service="$1"
  local env_var="$2"
  local db_url="$3"

  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo "▶ $service  ($env_var)"
  echo "═══════════════════════════════════════════════════════════"

  local app_dir="apps/$service"
  if [ ! -f "$app_dir/alembic.ini" ]; then
    echo "SKIP: $app_dir/alembic.ini no existe"
    return 0
  fi

  if $DRY_RUN; then
    echo "[dry-run] cd $app_dir && export ${env_var}='${db_url}' && alembic upgrade head"
  else
    pushd "$app_dir" > /dev/null
    export "${env_var}=${db_url}"
    alembic current
    alembic upgrade head
    alembic current
    popd > /dev/null
  fi
}

echo "Platform migrations runner"
echo "Dry run: $DRY_RUN"

# Orden importa: academic primero (otros referencian users/comisiones por UUID
# pero no FK, así que técnicamente no hay dep; pero por convención operacional).
# evaluation-service comparte la DB academic_main con academic-service
# (CLAUDE.md "Cuatro bases logicas") — por eso recibe ACADEMIC_DB_URL y debe
# correr DESPUES de academic para que las tablas FK-referenciadas existan.
# Usa una version_table propia (alembic_version_evaluation) para no chocar.
run_migration "academic-service" "ACADEMIC_DB_URL" "$ACADEMIC_DB_URL"
run_migration "evaluation-service" "ACADEMIC_DB_URL" "$ACADEMIC_DB_URL"
run_migration "ctr-service"      "CTR_DB_URL"   "$CTR_DB_URL"
run_migration "classifier-service" "CLASSIFIER_DB_URL" "$CLASSIFIER_DB_URL"
run_migration "content-service"  "CONTENT_DB_URL"  "$CONTENT_DB_URL"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✓ Migraciones completadas"
echo "═══════════════════════════════════════════════════════════"
