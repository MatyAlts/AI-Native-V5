#!/usr/bin/env bash
# scripts/smoke-test-attestation.sh - smoke test del flujo attestation E2E (ADR-021).
#
# Requiere:
#   - El integrity-attestation-service corriendo en :8012 (o ATTESTATION_URL).
#   - Tener el JSON correctamente formateado (UUIDs, hash 64 hex, ts con Z).
#
# Uso:
#   scripts/smoke-test-attestation.sh                    # http://127.0.0.1:8012 default
#   scripts/smoke-test-attestation.sh http://otro:8012   # override URL
#
# Pre-requisito: levantar el servicio antes
#   cd <repo-root>
#   uv run uvicorn integrity_attestation_service.main:app --port 8012 --reload
#
# Que valida:
#   1. /health responde 200
#   2. /api/v1/attestations/pubkey devuelve un PEM con header X-Signer-Pubkey-Id
#   3. POST /api/v1/attestations con payload valido devuelve 201 + attestation
#   4. POST con final_chain_hash invalido devuelve 422 (Pydantic validation)
#   5. GET /api/v1/attestations/{date} devuelve el JSONL del dia con la attestation
#   6. La firma de la attestation valida con la pubkey via verify-attestations.py

set -euo pipefail

ATT_URL="${1:-http://127.0.0.1:8012}"
TMP_DIR=$(mktemp -d -t att-smoke-XXXXXX)
FAILED=0

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

check() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  [OK]   $label ($actual)"
    else
        echo "  [FAIL] $label — esperado $expected, obtenido $actual"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== Smoke test attestation flow ==="
echo "Service URL: $ATT_URL"
echo ""

# ── 1. Health ─────────────────────────────────────────────────────────
echo "[1] Health"
status=$(curl -o /dev/null -s -w "%{http_code}" -m 5 "$ATT_URL/health" || echo "000")
check "GET /health" "$status" "200"

# ── 2. Pubkey ─────────────────────────────────────────────────────────
echo ""
echo "[2] Pubkey publica"
curl -s -m 5 -D "$TMP_DIR/pubkey.headers" "$ATT_URL/api/v1/attestations/pubkey" -o "$TMP_DIR/pubkey.pem"
status=$(grep -i "^HTTP" "$TMP_DIR/pubkey.headers" | tail -1 | awk '{print $2}' || echo "000")
check "GET /pubkey status" "$status" "200"

if grep -q "BEGIN PUBLIC KEY" "$TMP_DIR/pubkey.pem"; then
    echo "  [OK]   PEM tiene formato valido"
else
    echo "  [FAIL] PEM no parece valido"
    FAILED=$((FAILED + 1))
fi

pubkey_id=$(grep -i "^x-signer-pubkey-id" "$TMP_DIR/pubkey.headers" | awk '{print $2}' | tr -d '\r' || echo "")
if [ -n "$pubkey_id" ]; then
    echo "  [OK]   X-Signer-Pubkey-Id presente: $pubkey_id"
else
    echo "  [FAIL] X-Signer-Pubkey-Id ausente"
    FAILED=$((FAILED + 1))
fi

# ── 3. POST attestation valida ─────────────────────────────────────────
echo ""
echo "[3] POST attestation valida"
read -r -d '' VALID_PAYLOAD <<'EOF' || true
{
  "episode_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "final_chain_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "total_events": 42,
  "ts_episode_closed": "2026-04-27T10:30:00Z"
}
EOF

response=$(curl -s -m 5 -w "\n%{http_code}" -X POST -H "Content-Type: application/json" \
    -d "$VALID_PAYLOAD" "$ATT_URL/api/v1/attestations" || echo "ERROR\n000")
status=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')
check "POST status" "$status" "201"

if echo "$body" | grep -q '"signature"'; then
    echo "  [OK]   Response incluye signature"
else
    echo "  [FAIL] Response sin signature: $body"
    FAILED=$((FAILED + 1))
fi

# ── 4. POST con hash invalido (esperamos 422) ─────────────────────────
echo ""
echo "[4] POST con hash invalido (debe fallar 422)"
read -r -d '' BAD_PAYLOAD <<'EOF' || true
{
  "episode_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "final_chain_hash": "not-hex",
  "total_events": 42,
  "ts_episode_closed": "2026-04-27T10:30:00Z"
}
EOF

status=$(curl -o /dev/null -s -w "%{http_code}" -m 5 -X POST -H "Content-Type: application/json" \
    -d "$BAD_PAYLOAD" "$ATT_URL/api/v1/attestations" || echo "000")
check "POST con hash invalido" "$status" "422"

# ── 5. GET JSONL del dia ──────────────────────────────────────────────
echo ""
echo "[5] GET JSONL del dia"
today=$(date -u +%Y-%m-%d)
status=$(curl -o "$TMP_DIR/journal.jsonl" -s -w "%{http_code}" -m 5 \
    "$ATT_URL/api/v1/attestations/$today" || echo "000")
check "GET /attestations/$today" "$status" "200"

if [ -s "$TMP_DIR/journal.jsonl" ]; then
    lines=$(wc -l < "$TMP_DIR/journal.jsonl")
    echo "  [OK]   Journal con $lines linea(s)"
else
    echo "  [FAIL] Journal vacio"
    FAILED=$((FAILED + 1))
fi

# ── 6. Verificar firma con la tool CLI (si esta disponible) ───────────
echo ""
echo "[6] Verificacion criptografica con verify-attestations.py"
if command -v uv >/dev/null && [ -f scripts/verify-attestations.py ]; then
    if uv run python scripts/verify-attestations.py \
        --jsonl-dir "$TMP_DIR" \
        --pubkey-pem "$TMP_DIR/pubkey.pem" >"$TMP_DIR/verify.out" 2>&1; then
        echo "  [OK]   Tool verifico todas las firmas (exit 0)"
    else
        echo "  [FAIL] Tool reporto firmas invalidas (exit no-cero)"
        cat "$TMP_DIR/verify.out"
        FAILED=$((FAILED + 1))
    fi
else
    echo "  [SKIP] uv o scripts/verify-attestations.py no disponible"
fi

# ── Resumen ────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
if [ "$FAILED" -gt 0 ]; then
    echo "[FAIL] $FAILED chequeo(s) fallaron"
    exit 1
fi
echo "[OK] Todos los smoke tests pasaron"
