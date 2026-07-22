#!/usr/bin/env bash
# Chequea que todos los servicios respondan a /health/ready.
# Parsea el JSON: distingue ready / degraded / error y muestra qué checks fallan.
#
# Uso: ./scripts/check-health.sh
# Requiere: jq

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq no esta instalado. Instalar con apt/brew."
    exit 2
fi

declare -A SERVICES=(
    ["api-gateway"]=8000
    ["academic-service"]=8002
    ["evaluation-service"]=8004
    ["analytics-service"]=8005
    ["tutor-service"]=8006
    ["ctr-service"]=8007
    ["classifier-service"]=8008
    ["content-service"]=8009
    ["governance-service"]=8010
    ["ai-gateway"]=8011
    ["integrity-attestation-service"]=8012
)
# Nota: integrity-attestation-service (ADR-021) en piloto vive en infra
# institucional separada — el "no responde" desde local NO es un problema en prod.
# identity-service deprecated por ADR-041 (auth via api-gateway).
# enrollment-service deprecated por ADR-030 (bulk-import via academic-service).

declare -A FRONTENDS=(
    ["web-admin"]=5173
    ["web-teacher"]=5174
    ["web-student"]=5175
)

echo "---- Backend services ----"
failed=0
degraded=0
for svc in "${!SERVICES[@]}"; do
    port="${SERVICES[$svc]}"
    url="http://127.0.0.1:${port}/health/ready"

    # -w "%{http_code}" para capturar status code junto al body. -o pipe el body.
    body_file=$(mktemp)
    http_code=$(curl -sS -m 3 -o "${body_file}" -w "%{http_code}" "${url}" 2>/dev/null || echo "000")
    body=$(cat "${body_file}")
    rm -f "${body_file}"

    if [ "${http_code}" = "000" ]; then
        echo -e "  ${RED}[FAIL]${NC} ${svc} (:${port}) -- no responde"
        failed=$((failed + 1))
        continue
    fi

    # Parse JSON con jq. Si no es JSON valido, fallar gracioso.
    status=$(echo "${body}" | jq -r '.status // "unknown"' 2>/dev/null || echo "unknown")
    failed_checks=$(
        echo "${body}" \
            | jq -r '.checks // {} | to_entries | map(select(.value.ok == false)) | map(.key + "=" + (.value.error // "down")) | join(", ")' \
            2>/dev/null \
            || echo ""
    )

    case "${status}" in
        ready)
            echo -e "  ${GREEN}[OK]${NC}    ${svc} (:${port})"
            ;;
        degraded)
            echo -e "  ${YELLOW}[WARN]${NC}  ${svc} (:${port}) -- degraded: ${failed_checks}"
            degraded=$((degraded + 1))
            ;;
        error)
            echo -e "  ${RED}[FAIL]${NC} ${svc} (:${port}) -- error (${http_code}): ${failed_checks}"
            failed=$((failed + 1))
            ;;
        *)
            # Fallback: solo status code (para servicios que aun no implementan checks).
            if [ "${http_code}" -ge 200 ] && [ "${http_code}" -lt 300 ]; then
                echo -e "  ${GREEN}[OK]${NC}    ${svc} (:${port}) -- legacy 2xx (sin status field)"
            else
                echo -e "  ${RED}[FAIL]${NC} ${svc} (:${port}) -- HTTP ${http_code}"
                failed=$((failed + 1))
            fi
            ;;
    esac
done

echo ""
echo "---- Frontends ----"
for app in "${!FRONTENDS[@]}"; do
    port="${FRONTENDS[$app]}"
    if curl -fsS -m 3 "http://127.0.0.1:${port}" > /dev/null 2>&1; then
        echo -e "  ${GREEN}[OK]${NC}    ${app} (:${port})"
    else
        echo -e "  ${YELLOW}[--]${NC}    ${app} (:${port}) -- no corriendo (OK si no hicieron pnpm dev)"
    fi
done

echo ""
total_warn="${degraded}"
if [ "$failed" -gt 0 ]; then
    echo -e "${RED}Total: ${failed} backend(s) en error, ${total_warn} degraded${NC}"
    exit 1
elif [ "${total_warn}" -gt 0 ]; then
    echo -e "${YELLOW}Backends OK con ${total_warn} degraded (non-critical deps caidas)${NC}"
    exit 0
else
    echo -e "${GREEN}Todos los backends OK${NC}"
fi
