#!/usr/bin/env bash
# start-video-ready.sh
#
# Levanta el stack listo para grabar el video:
#   1. Verifica infra Docker (postgres, redis, keycloak, etc.)
#   2. Levanta los 11 backends + 8 ctr-workers
#   3. Verifica que copilot-api este corriendo en :4141
#   4. Reinicia api-gateway con DEV_TRUST_HEADERS=true
#   5. Reinicia ai-gateway + tutor-service apuntando a copilot-api (gpt-4o-mini)
#   6. Levanta los 3 frontends Vite
#   7. Verifica que la unidad "test" + TP-EDAD-01 + ejercicio "edad" existan
#      (si no, los crea desde seed-video-ejercicio.sql)
#
# Idempotente: corre N veces sin romper nada.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[--]${NC} $1"; }
log_err()  { echo -e "${RED}[FAIL]${NC} $1"; }

echo "==> 1/7 Verificando infra Docker ..."
if ! docker ps --format '{{.Names}}' | grep -q "platform-postgres"; then
  log_warn "Infra Docker no esta arriba. Levantando ..."
  docker compose -f infrastructure/docker-compose.dev.yml up -d
  echo "Esperando 10s a que la infra arranque ..."
  sleep 10
fi
log_ok "Infra Docker arriba"

echo ""
echo "==> 2/7 Verificando que copilot-api este corriendo en :4141 ..."
if ! curl -s -f -o /dev/null http://localhost:4141/models; then
  log_err "copilot-api NO esta corriendo en :4141"
  echo ""
  echo "Para arrancarlo:"
  echo "  Terminal aparte: npx -y copilot-api@latest start --port 4141"
  echo "Si nunca lo autenticaste:"
  echo "  npx -y copilot-api@latest auth"
  echo ""
  exit 1
fi
log_ok "copilot-api respondiendo en :4141"

echo ""
echo "==> 3/7 Apagando backends previos (si hay) ..."
bash scripts/dev-stop-all.sh 2>/dev/null || true
sleep 2
log_ok "Backends previos apagados"

echo ""
echo "==> 4/7 Levantando 11 backends + 8 ctr-workers ..."
bash scripts/dev-start-all.sh > /dev/null 2>&1
echo "Esperando que los 11 backends queden healthy ..."
until curl -sf http://localhost:8000/health > /dev/null \
      && curl -sf http://localhost:8002/health > /dev/null \
      && curl -sf http://localhost:8006/health > /dev/null \
      && curl -sf http://localhost:8007/health > /dev/null \
      && curl -sf http://localhost:8008/health > /dev/null \
      && curl -sf http://localhost:8010/health > /dev/null \
      && curl -sf http://localhost:8011/health > /dev/null; do
  sleep 2
done
log_ok "11 backends healthy"

echo ""
echo "==> 5/7 Reiniciando api-gateway con DEV_TRUST_HEADERS=true ..."
API_GW_PID=$(grep "^[0-9]*:api-gateway:" .dev-logs/pids.txt | cut -d: -f1)
kill "$API_GW_PID" 2>/dev/null || true
sleep 2
DEV_TRUST_HEADERS=true nohup uv run uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000 \
  > .dev-logs/api-gateway.log 2>&1 &
until curl -sf http://localhost:8000/health > /dev/null; do sleep 1; done
log_ok "api-gateway con DEV_TRUST_HEADERS=true"

echo ""
echo "==> 6/7 Reiniciando ai-gateway + tutor-service apuntando a copilot-api ..."
bash scripts/dev-use-copilot-api.sh > /dev/null 2>&1
log_ok "LLM via copilot-api (gpt-4o-mini)"

echo ""
echo "==> 7/7 Verificando que el ejercicio del video exista ..."
EXERCISE_EXISTS=$(docker exec platform-postgres psql -U postgres -d academic_main -tAc \
  "SELECT count(*) FROM ejercicios WHERE id='bbbbbbbb-eeee-dddd-dddd-000000000099';" 2>/dev/null || echo "0")

if [ "$EXERCISE_EXISTS" = "0" ]; then
  log_warn "Ejercicio del video NO existe. Aplicando seed ..."
  docker cp scripts/seed-video-ejercicio.sql platform-postgres:/tmp/seed-video-ejercicio.sql
  docker exec platform-postgres psql -U postgres -d academic_main \
    -f /tmp/seed-video-ejercicio.sql > /dev/null
  log_ok "Seed del video aplicado"
else
  log_ok "Ejercicio del video ya existe"
fi

echo ""
echo "==> Levantando los 3 frontends Vite ..."
nohup make dev > .dev-logs/frontends.log 2>&1 &
echo "Esperando que :5173, :5174, :5175 respondan ..."
until curl -sf http://localhost:5173 > /dev/null \
      && curl -sf http://localhost:5174 > /dev/null \
      && curl -sf http://localhost:5175 > /dev/null; do
  sleep 2
done
log_ok "3 frontends arriba"

echo ""
echo "============================================================"
echo -e "${GREEN}STACK LISTO PARA GRABAR${NC}"
echo "============================================================"
echo ""
echo "  Alumno:   http://localhost:5175"
echo "  Docente:  http://localhost:5174"
echo "  Admin:    http://localhost:5173"
echo "  API:      http://localhost:8000"
echo "  Grafana:  http://localhost:3000  (admin/admin)"
echo ""
echo "Flujo para grabar:"
echo "  1. Abri http://localhost:5175"
echo "  2. Click en 'Programación I' → 'Entrar'"
echo "  3. Click en unidad 'test #99'"
echo "  4. Click en 'TP-EDAD-01' → 'Empezar'"
echo "  5. Click en 'Ejercicio 1: Categoria por edad' → 'Empezar'"
echo ""
echo "Para apagar todo:"
echo "  bash scripts/dev-stop-all.sh && pkill -f 'vite'"
echo ""
