#!/bin/bash
# Reinicia ai-gateway + tutor-service para usar copilot-api como provider OpenAI.
#
# Pre-requisitos:
#   1. Tener corriendo copilot-api en localhost:4141:
#        # Una sola vez:
#        npx -y copilot-api@latest auth
#        # En cada arranque (en otra terminal):
#        npx -y copilot-api@latest start --port 4141
#
#   2. Servicios platform infra arriba (postgres, redis, etc.):
#        docker compose -f infrastructure/docker-compose.dev.yml up -d
#
#   3. Los servicios platform Python arrancados con dev-start-all.sh.
#
# Lo que hace este script:
#   - Mata el ai-gateway y el tutor-service actuales (si están corriendo).
#   - Vuelve a arrancarlos con LLM_PROVIDER=openai apuntando al proxy local.
#   - El default_model del tutor ya es gpt-4o-mini (ver config.py).
#
# Para volver a Mistral / Anthropic real: rotar BYOK key vía POST /api/v1/byok/keys
# o reactivar la key Mistral revocada con UPDATE byok_keys SET revoked_at=NULL.

set -euo pipefail

PROXY_URL="${COPILOT_API_URL:-http://localhost:4141/v1}"
PROXY_HEALTH="${COPILOT_API_URL:-http://localhost:4141}/models"

echo "==> 1/4 Verificando que copilot-api esté corriendo en $PROXY_URL ..."
if ! curl -s -f -o /dev/null "$PROXY_HEALTH" 2>&1; then
    echo
    echo "ERROR: copilot-api no responde en $PROXY_HEALTH"
    echo
    echo "Para arrancarlo en OTRA terminal:"
    echo "    npx -y copilot-api@latest start --port 4141"
    echo
    echo "Si es la primera vez, autorizá GitHub primero:"
    echo "    npx -y copilot-api@latest auth"
    echo
    exit 1
fi
echo "    OK"

echo "==> 2/4 Matando ai-gateway y tutor-service actuales (si están corriendo) ..."
pkill -f "ai_gateway.main:app" 2>/dev/null || true
pkill -f "tutor_service.main:app" 2>/dev/null || true
sleep 1

echo "==> 3/4 Relanzando ai-gateway con LLM_PROVIDER=openai + base_url al proxy ..."
mkdir -p .dev-logs
LLM_PROVIDER=openai \
OPENAI_BASE_URL="$PROXY_URL" \
OPENAI_API_KEY="copilot-proxy-no-key-needed" \
EMBEDDER=mock \
STORAGE=mock \
nohup uv run uvicorn ai_gateway.main:app \
    --host 127.0.0.1 --port 8011 --log-level info \
    > .dev-logs/ai-gateway.log 2>&1 &
echo "    PID $!"

echo "==> 4/4 Relanzando tutor-service (ya configurado con default_model=gpt-4o-mini) ..."
nohup uv run uvicorn tutor_service.main:app \
    --host 127.0.0.1 --port 8006 --log-level info \
    > .dev-logs/tutor-service.log 2>&1 &
echo "    PID $!"

sleep 3

echo
echo "==> Verificación health checks:"
echo -n "    ai-gateway:   "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8011/health/ready
echo -n "    tutor:        "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8006/health

echo
echo "Listo. Abrí el web-student en http://localhost:5175 y probá un episodio."
echo "Si querés ver los logs en vivo:"
echo "    tail -f .dev-logs/ai-gateway.log"
echo "    tail -f .dev-logs/tutor-service.log"
