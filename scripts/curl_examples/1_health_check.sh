#!/usr/bin/env bash
# =============================================================================
# health_check.sh — Verify the gateway and all backing services
# =============================================================================
# Usage:
#   bash scripts/curl_examples/health_check.sh
#   bash scripts/curl_examples/health_check.sh --debug
# =============================================================================

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
DEBUG="${1:-}"
USERNAME="platform0"
PASSWORD="123456"

login() {
  local response
  response=$(curl -s -X POST "${GATEWAY_URL}/v1/auth/login" \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d "{
      \"username\": \"${USERNAME}\",
      \"password\": \"${PASSWORD}\"
    }")

  echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))"
}

echo "═══════════════════════════════════════════"
echo "  Gateway Health Check"
if [[ "$DEBUG" == "--debug" ]]; then
  echo "  ${GATEWAY_URL}/health/debug"
else
  echo "  ${GATEWAY_URL}/health"
fi
echo "═══════════════════════════════════════════"

if [[ "$DEBUG" == "--debug" ]]; then
  TOKEN="$(login)"

  if [[ -z "$TOKEN" ]]; then
    echo "Không lấy được token. Kiểm tra TENANT_ID, USERNAME, PASSWORD hoặc API login."
    exit 1
  fi

  curl -s "${GATEWAY_URL}/health/debug" \
    -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
else
  curl -s "${GATEWAY_URL}/health" | python3 -m json.tool
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Gateway Version"
echo "  ${GATEWAY_URL}/version"
echo "═══════════════════════════════════════════"

curl -s "${GATEWAY_URL}/version" | python3 -m json.tool
