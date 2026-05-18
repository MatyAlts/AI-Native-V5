#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .dev-logs
: > .dev-logs/pids.txt

# Mock providers (ADR — sin API keys reales en dev)
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
export EMBEDDER="${EMBEDDER:-mock}"
export RERANKER="${RERANKER:-identity}"
export STORAGE="${STORAGE:-mock}"

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
