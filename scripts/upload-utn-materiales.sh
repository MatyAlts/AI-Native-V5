#!/usr/bin/env bash
# Sube los archivos de documentos/ como materiales del RAG para la materia
# Programacion I (PROG1) del seed-utn-vps.py.
#
# Pre-requisitos:
#   - Stack arriba (academic-service + ai-gateway en :8000 via api-gateway)
#   - seed-utn-vps.py ya ejecutado (creo la materia PROG1 con MATERIA_ID).
#   - api-gateway con DEV_TRUST_HEADERS=true (dev local) o JWT de docente
#     con rol docente_admin (prod con Keycloak).
#
# Uso:
#   bash scripts/upload-utn-materiales.sh
#   bash scripts/upload-utn-materiales.sh --gateway-url https://mi-vps.utn.edu.ar
#
# Variables env opcionales:
#   GATEWAY_URL          (default: http://127.0.0.1:8000)
#   TENANT_ID            (default: d0d0d0d0-0000-0000-0000-d0d0d0d00000)
#   MATERIA_ID           (default: d0d0d0d0-aa01-aa01-aa01-d0d0d0d0aa01)
#   DOCENTE_USER_ID      (default: d0d0d0d0-d0c1-d0c1-d0c1-d0d0d0d0c001)
#   DOCS_DIR             (default: documentos)
#   BEARER_TOKEN         (default: "" — usa dev_trust_headers)

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8000}"
TENANT_ID="${TENANT_ID:-d0d0d0d0-0000-0000-0000-d0d0d0d00000}"
MATERIA_ID="${MATERIA_ID:-d0d0d0d0-aa01-aa01-aa01-d0d0d0d0aa01}"
DOCENTE_USER_ID="${DOCENTE_USER_ID:-d0d0d0d0-d0c1-d0c1-d0c1-d0d0d0d0c001}"
DOCS_DIR="${DOCS_DIR:-documentos}"
BEARER_TOKEN="${BEARER_TOKEN:-}"

# Args parse
while [[ $# -gt 0 ]]; do
  case "$1" in
    --gateway-url) GATEWAY_URL="$2"; shift 2 ;;
    --bearer) BEARER_TOKEN="$2"; shift 2 ;;
    *) echo "Arg desconocido: $1" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

if [[ ! -d "$DOCS_DIR" ]]; then
  echo "[upload-utn-materiales] ERROR: '$DOCS_DIR' no existe en $(pwd)" >&2
  exit 1
fi

# Auth headers — JWT real en prod o dev_trust_headers en local
auth_args=()
if [[ -n "$BEARER_TOKEN" ]]; then
  auth_args=(-H "Authorization: Bearer $BEARER_TOKEN")
else
  auth_args=(
    -H "X-Tenant-Id: $TENANT_ID"
    -H "X-User-Id: $DOCENTE_USER_ID"
    -H "X-User-Email: docente@utn.edu.ar"
    -H "X-User-Roles: docente_admin,docente,superadmin"
  )
fi

echo "[upload-utn-materiales] gateway=$GATEWAY_URL materia=$MATERIA_ID dir=$DOCS_DIR"
echo ""

uploaded=0
skipped=0
failed=0
for f in "$DOCS_DIR"/*.pdf "$DOCS_DIR"/*.docx "$DOCS_DIR"/*.md; do
  [[ ! -f "$f" ]] && continue
  filename=$(basename "$f")
  size_kb=$(( $(stat -c%s "$f") / 1024 ))
  echo "  -> $filename (${size_kb} KB) ..."
  if curl -sS -f \
       "${auth_args[@]}" \
       -F "file=@${f}" \
       -F "materia_id=${MATERIA_ID}" \
       -F "titulo=${filename%.*}" \
       -F "tipo=apunte" \
       "${GATEWAY_URL}/api/v1/materiales" \
       -o /dev/null; then
    uploaded=$((uploaded + 1))
    echo "     OK"
  else
    failed=$((failed + 1))
    echo "     FAIL"
  fi
done

echo ""
echo "[upload-utn-materiales] uploaded=$uploaded skipped=$skipped failed=$failed"
if [[ $failed -gt 0 ]]; then
  exit 1
fi
