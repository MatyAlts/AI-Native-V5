#!/bin/sh
# Entrypoint del container ctr-service. Detecta si arranca como server HTTP
# o como worker de partition.
#
# Variables:
#   CTR_MODE=server (default): arranca uvicorn en :8007
#   CTR_MODE=worker + CTR_WORKER_PARTITION=N: arranca partition_worker
#
# Importante: usa /app/.venv/bin/python con path absoluto explicito porque
# EasyPanel u otros orquestadores pueden generar un docker-compose.override
# que pisa el `command:` del compose y desreferencia el python del venv
# (cayendo al /usr/bin/python del base image, que no tiene el venv activo).
set -eu

VENV_PY="/app/.venv/bin/python"

# ── Esperar dependencias (Postgres + Redis) antes de migrar/arrancar ──────
# Sin esto, al levantar el stack el ctr-service puede ganarle la carrera al
# boot/DNS de Postgres/Redis y crashear con gaierror "Name or service not
# known" (paso real 2026-06: los 8 workers murieron al arrancar y un episodio
# quedo integrity_compromised). Reintenta hasta ~2 min y recien ahi falla.
wait_for_tcp() {
  # $1=host  $2=port  $3=nombre
  [ -n "$1" ] || { echo "[ctr-entrypoint] $3: host vacio, no espero"; return 0; }
  i=1
  while [ "$i" -le 60 ]; do
    if "$VENV_PY" -c "import socket; socket.create_connection(('$1', int('$2')), 2).close()" 2>/dev/null; then
      echo "[ctr-entrypoint] $3 disponible ($1:$2)"
      return 0
    fi
    echo "[ctr-entrypoint] esperando $3 ($1:$2)... intento $i/60"
    i=$((i + 1))
    sleep 2
  done
  echo "[ctr-entrypoint] ERROR: timeout esperando $3 ($1:$2)" >&2
  return 1
}

url_part() {
  # $1=nombre de env var con una URL  $2=atributo (hostname|port)
  "$VENV_PY" -c "import os,urllib.parse as u; p=u.urlparse(os.environ.get('$1','').replace('+asyncpg','')); print(getattr(p,'$2') or '')" 2>/dev/null || true
}

DB_URL_VAR="CTR_DB_URL"
[ -n "${CTR_DB_URL:-}" ] || DB_URL_VAR="CTR_STORE_URL"
PG_HOST=$(url_part "$DB_URL_VAR" hostname); PG_PORT=$(url_part "$DB_URL_VAR" port); [ -n "$PG_PORT" ] || PG_PORT=5432
RD_HOST=$(url_part REDIS_URL hostname);     RD_PORT=$(url_part REDIS_URL port);     [ -n "$RD_PORT" ] || RD_PORT=6379
wait_for_tcp "$PG_HOST" "$PG_PORT" "Postgres"
wait_for_tcp "$RD_HOST" "$RD_PORT" "Redis"

# ── Migraciones (fallar duro) ─────────────────────────────────────────────
# Con la DB ya disponible (wait_for arriba), un fallo de alembic aca es un
# problema real de schema → mejor NO arrancar que correr con schema viejo.
# Verificado 2026-06-03: current == head (20260721_0002) → upgrade es no-op
# salvo migraciones nuevas. Antes habia "|| continuing anyway" que enmascaraba
# el fallo y arrancaba igual.
ALEMBIC_DIR="/app/apps/ctr-service"
[ -d "$ALEMBIC_DIR" ] || ALEMBIC_DIR="/app"
cd "$ALEMBIC_DIR" && "$VENV_PY" -m alembic upgrade head
cd /app

case "${CTR_MODE:-server}" in
  worker)
    if [ -z "${CTR_WORKER_PARTITION:-}" ]; then
      echo "ERROR: CTR_MODE=worker requiere CTR_WORKER_PARTITION (0-7)" >&2
      exit 2
    fi
    echo "[ctr-entrypoint] arrancando worker partition=${CTR_WORKER_PARTITION}"
    exec "$VENV_PY" -m ctr_service.workers.partition_worker --partition "${CTR_WORKER_PARTITION}"
    ;;
  server|*)
    echo "[ctr-entrypoint] arrancando workers partition 0-7 en background"
    for p in 0 1 2 3 4 5 6 7; do
      "$VENV_PY" -m ctr_service.workers.partition_worker --partition "$p" &
    done
    echo "[ctr-entrypoint] arrancando HTTP server :8007"
    exec "$VENV_PY" -m uvicorn ctr_service.main:app --host 0.0.0.0 --port 8007
    ;;
esac
