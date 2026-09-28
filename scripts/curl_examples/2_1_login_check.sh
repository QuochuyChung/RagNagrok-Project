#!/usr/bin/env bash
# =============================================================================
# 2_1_login_check.sh — Login and Role-Based Access Control (RBAC) verification
# =============================================================================
# Usage:
#   bash scripts/curl_examples/2_1_login_check.sh
# =============================================================================

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"

# Helper function to perform login and output JWT access token
login() {
  local username="$1"
  local password="$2"
  local response
  
  response=$(curl -s -X POST "${GATEWAY_URL}/v1/auth/login" \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    -d "{
      \"username\": \"${username}\",
      \"password\": \"${password}\"
    }")
  
  echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo ""
}

# Helper function to list users with a Bearer token
list_users() {
  local token="$1"
  curl -s -X GET "${GATEWAY_URL}/v1/users" \
    -H "Authorization: Bearer ${token}" \
    -H 'Accept: application/json'
}

echo "═══════════════════════════════════════════════════════════════════"
echo "  RBAC Test Flow (Platform Admin vs. Tenant Admin vs. User)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# 1. Platform Admin
echo "--- PLATFORM_ADMIN ---"
PA_TOKEN=$(login "platform0" "123456")

if [[ -z "$PA_TOKEN" ]]; then
  echo "❌ Login failed for platform_admin"
  exit 1
fi
echo "✓ Login successful."

PA_USERS_RESP=$(list_users "$PA_TOKEN")
PA_TOTAL=$(echo "$PA_USERS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total', ''))" 2>/dev/null || echo "")

if [[ -n "$PA_TOTAL" ]]; then
  echo "Users found: $PA_TOTAL (Expected: 3)"
else
  echo "❌ Failed to query users or parse response: $PA_USERS_RESP"
  exit 1
fi
echo ""

# 2. Tenant Admin
echo "--- TENANT_ADMIN ---"
TA_TOKEN=$(login "tenant0" "123456")

if [[ -z "$TA_TOKEN" ]]; then
  echo "❌ Login failed for tenant0"
  exit 1
fi
echo "✓ Login successful."

TA_USERS_RESP=$(list_users "$TA_TOKEN")
TA_TOTAL=$(echo "$TA_USERS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total', ''))" 2>/dev/null || echo "")

if [[ -n "$TA_TOTAL" ]]; then
  echo "Users found: $TA_TOTAL (Expected: 3)"
else
  echo "❌ Failed to query users or parse response: $TA_USERS_RESP"
  exit 1
fi
echo ""

# 3. User
echo "--- USER ---"
U_TOKEN=$(login "user0" "123456")

if [[ -z "$U_TOKEN" ]]; then
  echo "❌ Login failed for user0"
  exit 1
fi
echo "✓ Login successful."

# Perform request and capture both status code and response body
U_USERS_RESP_FILE=$(mktemp)
U_STATUS_CODE=$(curl -s -X GET "${GATEWAY_URL}/v1/users" \
  -H "Authorization: Bearer ${U_TOKEN}" \
  -H 'Accept: application/json' \
  -w "%{http_code}" -o "$U_USERS_RESP_FILE")

U_RESP_CONTENT=$(cat "$U_USERS_RESP_FILE")
rm -f "$U_USERS_RESP_FILE"

if [[ "$U_STATUS_CODE" == "403" ]]; then
  echo "✓ Access forbidden as expected (HTTP 403 Forbidden)."
  echo "Response detail: $U_RESP_CONTENT"
else
  echo "❌ FAILED: User should not be able to list users!"
  echo "HTTP Status: $U_STATUS_CODE"
  echo "Response detail: $U_RESP_CONTENT"
  exit 1
fi

echo ""
echo "✨ RBAC test flow complete!"
