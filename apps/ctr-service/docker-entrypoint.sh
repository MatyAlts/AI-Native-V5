#!/bin/sh
# Entrypoint del container ctr-service. Detecta si arranca como server HTTP
# o como worker de partition.
#
# Variables:
#   CTR_MODE=http: SOLO uvicorn en :8007 (sin workers in-process). Usar en prod
#     cuando los partition_worker corren en containers dedicados (ctr-worker-N).
#   CTR_MODE=server (default): uvicorn en :8007 + los 8 partition_worker
#     in-process (monolitico single-node; dev/local). NO combinar con containers
#     ctr-worker-N dedicados => duplicaria writers por particion (ver abajo).
#   CTR_MODE=worker + CTR_WORKER_PARTITION=N: arranca UN partition_worker.
#
# INVARIANTE single-writer por particion (ADR-010, NUM_PARTITIONS=8): cada
# particion 0..7 (stream Redis ctr.pN) debe ser drenada a Postgres por EXACTA-
# mente UN proceso worker en todo el cluster. Dos procesos sobre la misma
# particion (mismo consumer_group `ctr_workers` + mismo consumer_name
# `worker-N`) compiten por el PEL y procesan el mismo evento dos veces. El
# chain_hash NO se bifurca (SELECT FOR UPDATE sobre el episodio + validacion de
# seq + INSERT ON CONFLICT lo protegen); el dano real es entrega/procesamiento
# DESORDENADO -> seq != expected_seq -> ValueError -> dead-letter ->
# integrity_compromised PERMANENTE. Por eso `http` existe: en prod
# el ctr-service NO debe spawnear los workers que ya corren en ctr-worker-0..7.
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
  http)
    # HTTP-only: SOLO el server FastAPI. `ctr_service.main:app` NO spawnea
    # workers (su lifespan solo hace observabilidad), asi que este modo garantiza
    # que el ctr-service NO escribe ninguna particion. Los 8 partition_worker
    # corren en containers dedicados ctr-worker-0..7 (uno por particion) =>
    # single-writer por particion preservado (ADR-010).
    echo "[ctr-entrypoint] arrancando HTTP server :8007 (modo http, sin workers in-process)"
    exec "$VENV_PY" -m uvicorn ctr_service.main:app --host 0.0.0.0 --port 8007
    ;;
  server|*)
    # Monolitico single-node (dev/local): HTTP + los 8 workers in-process.
    # ADVERTENCIA: NO usar en un despliegue que TAMBIEN corre containers
    # ctr-worker-N dedicados. Ahi habria 2 writers por particion (el worker
    # in-process y el container) => rompe single-writer (ADR-010). En prod usar
    # CTR_MODE=http para el ctr-service y dejar los ctr-worker-N como unicos
    # writers.
    echo "[ctr-entrypoint] arrancando workers partition 0-7 en background (modo server monolitico)"
    for p in 0 1 2 3 4 5 6 7; do
      "$VENV_PY" -m ctr_service.workers.partition_worker --partition "$p" &
    done
    echo "[ctr-entrypoint] arrancando HTTP server :8007"
    exec "$VENV_PY" -m uvicorn ctr_service.main:app --host 0.0.0.0 --port 8007
    ;;
esac
