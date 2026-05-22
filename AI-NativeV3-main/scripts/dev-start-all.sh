#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .dev-logs
: > .dev-logs/pids.txt

# Providers reales por default (sin mocks).
#  - LLM_PROVIDER=gemini: el ai-gateway resuelve la key via BYOK (en
#    admin UI) o env GEMINI_API_KEY. Sin key configurada el tutor da
#    error claro en lugar de canned mock.
#  - EMBEDDER=local: sentence-transformers + multilingual-e5-large.
#    CUDA_VISIBLE_DEVICES="" fuerza CPU (la GPU local puede no tener
#    memoria libre; CPU es lento la primera vez pero estable).
#  - STORAGE=s3: MinIO local (corre en docker-compose.dev.yml :9000).
#    Las credenciales por default son minioadmin/minioadmin, alineadas
#    con `content-service/config.py` defaults.
#  - RERANKER=identity sigue siendo el default — no es mock, es
#    passthrough (sin reranking, el order del vector search se respeta).
#
# Override puntual: `LLM_PROVIDER=mock bash scripts/dev-start-all.sh`
# si necesitás canned responses para tests deterministicos.
export LLM_PROVIDER="${LLM_PROVIDER:-gemini}"
export EMBEDDER="${EMBEDDER:-local}"
export RERANKER="${RERANKER:-identity}"
export STORAGE="${STORAGE:-s3}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export S3_ENDPOINT="${S3_ENDPOINT:-http://127.0.0.1:9000}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
export S3_BUCKET_MATERIALS="${S3_BUCKET_MATERIALS:-materials}"

start_svc() {
  local module="$1"
  local port="$2"
  local name="$3"
  local log=".dev-logs/${name}.log"
  echo "[start] ${name} :${port}"
  uv run uvicorn "${module}:app" --host 127.0.0.1 --port "${port}" --log-level info \
    > "${log}" 2>&1 &
  echo "$!:${name}:${port}" >> .dev-logs/pids.txt
}

start_ctr_worker() {
  local partition="$1"
  local log=".dev-logs/ctr-worker-${partition}.log"
  echo "[start] ctr-worker partition=${partition}"
  uv run python -m ctr_service.workers.partition_worker --partition "${partition}" \
    > "${log}" 2>&1 &
  echo "$!:ctr-worker-${partition}:worker" >> .dev-logs/pids.txt
}

# 11 servicios HTTP (identity-service deprecated por ADR-041; enrollment-service por ADR-030)
start_svc api_gateway.main                    8000 api-gateway
start_svc academic_service.main               8002 academic-service
start_svc evaluation_service.main             8004 evaluation-service
start_svc analytics_service.main              8005 analytics-service
start_svc tutor_service.main                  8006 tutor-service
start_svc ctr_service.main                    8007 ctr-service
start_svc classifier_service.main             8008 classifier-service
start_svc content_service.main                8009 content-service
start_svc governance_service.main             8010 governance-service
start_svc ai_gateway.main                     8011 ai-gateway
start_svc integrity_attestation_service.main  8012 integrity-attestation-service

# 8 CTR partition workers (single-writer por particion, ADR-010)
for p in 0 1 2 3 4 5 6 7; do
  start_ctr_worker "$p"
done

echo ""
echo "Started 11 HTTP services + 8 CTR workers. Logs in .dev-logs/. PIDs in .dev-logs/pids.txt."
