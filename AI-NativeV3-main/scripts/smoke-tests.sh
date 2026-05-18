#!/usr/bin/env bash
# scripts/smoke-tests.sh - smoke tests post-deploy.
# Usar: scripts/smoke-tests.sh https://staging.plataforma.ar

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
FAILED=0

check() {
    local path="$1"
    local expected_status="${2:-200}"
    local url="${BASE_URL}${path}"
    local status
    status=$(curl -o /dev/null -s -w "%{http_code}" -m 10 "$url" || echo "000")
    if [ "$status" = "$expected_status" ]; then
        echo "  ✓ $path → $status"
    else
        echo "  ✗ $path → $status (esperado $expected_status)"
        FAILED=$((FAILED + 1))
    fi
}

echo "Smoke tests contra: $BASE_URL"
echo ""

check "/health" 200
check "/health/live" 200
check "/health/ready" 200

# Endpoint protegido debe responder 401 sin JWT
check "/api/v1/universidades" 401

echo ""
if [ "$FAILED" -gt 0 ]; then
    echo "✗ $FAILED smoke test(s) fallaron"
    exit 1
fi
echo "✓ Todos los smoke tests pasaron"
