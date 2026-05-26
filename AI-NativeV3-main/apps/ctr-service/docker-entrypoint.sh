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

# Run migrations before starting
ALEMBIC_DIR="/app/apps/ctr-service"
[ -d "$ALEMBIC_DIR" ] || ALEMBIC_DIR="/app"
cd "$ALEMBIC_DIR" && "$VENV_PY" -m alembic upgrade head || echo "[ctr-entrypoint] WARN: alembic migration failed, continuing anyway"
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
