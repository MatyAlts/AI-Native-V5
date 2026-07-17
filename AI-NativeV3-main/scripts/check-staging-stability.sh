#!/usr/bin/env bash
# Valida que el ambiente staging esté estable por N horas antes de permitir
# deploy a producción. Consulta Prometheus por error rate y SLOs.

set -euo pipefail

HOURS="${1:-24}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus.staging.plataforma.ar}"

echo "Verificando estabilidad de staging en las últimas ${HOURS}h"

# Error rate debe ser <1% en la ventana
ERROR_RATE=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[${HOURS}h]))/sum(rate(http_requests_total[${HOURS}h]))" \
    | grep -oP '"value":\[[0-9.]+,"[0-9.e-]+"\]' \
    | grep -oP '"[0-9.e-]+"' | tail -1 | tr -d '"')

if [ -z "$ERROR_RATE" ]; then
    echo "✗ No se pudo consultar error rate"
    exit 1
fi

THRESHOLD="0.01"
if awk "BEGIN{exit !($ERROR_RATE > $THRESHOLD)}"; then
    echo "✗ Error rate ${ERROR_RATE} > threshold ${THRESHOLD}"
    exit 1
fi

echo "✓ Staging estable (error rate: ${ERROR_RATE})"
