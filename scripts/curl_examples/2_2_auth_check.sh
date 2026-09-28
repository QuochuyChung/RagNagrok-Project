#!/usr/bin/env bash
# =============================================================================
# 2_2_auth_check.sh — Authentication check script
# =============================================================================
# Usage:
#   bash scripts/curl_examples/2_2_auth_check.sh
#   bash scripts/curl_examples/2_2_auth_check.sh --debug
# =============================================================================

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
DEBUG="${1:-}"

# Helper function to perform curl request, format JSON if possible, and output HTTP status
send_request() {
  local url="$1"
  local method="${2:-GET}"
  local token="${3:-}"
  local data="${4:-}"
  
  local curl_opts=("-s" "-X" "$method")
  if [[ -n "$token" ]]; then
    curl_opts+=("-H" "Authorization: Bearer $token")
  fi
  if [[ -n "$data" ]]; then
    curl_opts+=("-H" "Content-Type: application/json" "-d" "$data")
  fi
  
  local tmp_file
  tmp_file=$(mktemp)
  
  local status_code
  status_code=$(curl "${curl_opts[@]}" -w "%{http_code}" -o "$tmp_file" "$url")
  
  # Format output if it is valid JSON, otherwise print raw output
  if python3 -m json.tool "$tmp_file" >/dev/null 2>&1; then
    python3 -m json.tool "$tmp_file"
  else
    cat "$tmp_file"
    echo ""
  fi
  
  echo "HTTP Status: $status_code"
  rm -f "$tmp_file"
}

# Step 1: Public - No Auth Required
echo "═══════════════════════════════════════════════════════════════════"
echo "  STEP 1: Public - No Auth Required (Health & Version Check)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

echo "✓ Checking GET /health (Public):"
send_request "${GATEWAY_URL}/health"
echo ""

echo "✓ Checking GET /version (Public):"
send_request "${GATEWAY_URL}/version"
echo ""

# Step 2: Auth Required (No Token -> Expected UNAUTHORIZED) Endpoints In API Docs
echo "═══════════════════════════════════════════════════════════════════"
echo "  STEP 2: No Token Test - All Endpoints In API Docs"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

echo "───────────────────────────────────────────────────────────────────"
echo "  Infrastructure"
echo "───────────────────────────────────────────────────────────────────"
echo ""

echo "✓ Test calling GET /health without token:"
send_request "${GATEWAY_URL}/health"
echo ""

echo "✓ Test calling GET /health/debug without token:"
send_request "${GATEWAY_URL}/health/debug"
echo ""

echo "✓ Test calling GET /version without token:"
send_request "${GATEWAY_URL}/version"
echo ""

echo "✓ Test calling GET / without token:"
send_request "${GATEWAY_URL}/"
echo ""


echo "───────────────────────────────────────────────────────────────────"
echo "  Tenants"
echo "───────────────────────────────────────────────────────────────────"
echo ""

echo "✓ Test calling GET /v1/tenants without token:"
send_request "${GATEWAY_URL}/v1/tenants"
echo ""

echo "✓ Test calling POST /v1/tenants without token:"
send_request "${GATEWAY_URL}/v1/tenants" "POST" '{
  "name": "No Token Tenant"
}'
echo ""

echo "✓ Test calling GET /v1/tenants/{tenant_id} without token:"
send_request "${GATEWAY_URL}/v1/tenants/test-tenant-id"
echo ""

echo "✓ Test calling DELETE /v1/tenants/{tenant_id} without token:"
send_request "${GATEWAY_URL}/v1/tenants/test-tenant-id" "DELETE"
echo ""


echo "───────────────────────────────────────────────────────────────────"
echo "  Users"
echo "───────────────────────────────────────────────────────────────────"
echo ""

echo "✓ Test calling GET /v1/users without token:"
send_request "${GATEWAY_URL}/v1/users"
echo ""

echo "✓ Test calling POST /v1/users without token:"
send_request "${GATEWAY_URL}/v1/users" "POST" '{
  "email": "no.token.user@example.com",
  "name": "No Token User",
  "tenant_id": "test-tenant-id"
}'
echo ""

echo "✓ Test calling GET /v1/users/{user_id} without token:"
send_request "${GATEWAY_URL}/v1/users/test-user-id"
echo ""

echo "✓ Test calling DELETE /v1/users/{user_id} without token:"
send_request "${GATEWAY_URL}/v1/users/test-user-id" "DELETE"
echo ""


echo "───────────────────────────────────────────────────────────────────"
echo "  Auth"
echo "───────────────────────────────────────────────────────────────────"
echo ""

echo "✓ Test calling POST /v1/auth/login without token:"
send_request "${GATEWAY_URL}/v1/auth/login" "POST" '{
  "username": "admin",
  "password": "admin"
}'
echo ""


echo "───────────────────────────────────────────────────────────────────"
echo "  Documents"
echo "───────────────────────────────────────────────────────────────────"
echo ""

echo "✓ Test calling GET /v1/documents without token:"
send_request "${GATEWAY_URL}/v1/documents"
echo ""

echo "✓ Test calling POST /v1/documents without token:"
send_request "${GATEWAY_URL}/v1/documents" "POST"
echo ""

echo "✓ Test calling DELETE /v1/documents/{doc_id} without token:"
send_request "${GATEWAY_URL}/v1/documents/00000000-0000-0000-0000-000000000000" "DELETE"
echo ""

echo "✓ Test calling POST /v1/documents/{doc_id}/restore without token:"
send_request "${GATEWAY_URL}/v1/documents/00000000-0000-0000-0000-000000000000/restore" "POST"
echo ""


# Step 3: Login to get JWT Token
echo "═══════════════════════════════════════════════════════════════════"
echo "  STEP 3: Login để lấy JWT Token"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Cấu hình tài khoản login
USERNAME="platform0"
PASSWORD="123456"

LOGIN_RESPONSE=$(curl -s -X POST "${GATEWAY_URL}/v1/auth/login" \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{
    \"username\": \"${USERNAME}\",
    \"password\": \"${PASSWORD}\"
  }")

echo "📋 Login Response:"
if echo "$LOGIN_RESPONSE" | python3 -m json.tool >/dev/null 2>&1; then
  echo "$LOGIN_RESPONSE" | python3 -m json.tool
else
  echo "$LOGIN_RESPONSE"
fi

# Extract token
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('access_token', ''))" 2>/dev/null || echo "")

if [[ -z "$TOKEN" ]]; then
  echo ""
  echo "❌ Lỗi: Không lấy được token từ login response"
  echo "📝 Kiểm tra lại:"
  echo "   - Username: $USERNAME"
  echo "   - Kiểm tra container đang chạy: docker compose ps"
  exit 1
fi

echo ""
echo "✅ Đã lấy token thành công!"
echo "🔐 Token: ${TOKEN:0:50}..."
echo ""

# Step 4: Authenticated Debug Health Check (Optional/Debug)
if [[ "$DEBUG" == "--debug" ]]; then
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  STEP 4: Authenticated Debug Health Check"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""

  send_request "${GATEWAY_URL}/health/debug" "GET" "${TOKEN}"
  echo ""
fi

# Step 5: Test Protected Endpoint với Token
echo "═══════════════════════════════════════════════════════════════════"
echo "  STEP 5: Test Protected Endpoint (Cần Auth Token)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

echo "📤 Gọi: GET /v1/tenants"
send_request "${GATEWAY_URL}/v1/tenants" "GET" "${TOKEN}"
echo ""

echo "✨ Hoàn tất! Bạn đã login thành công và có thể sử dụng token này cho các API khác."
echo "📌 Lưu token nếu muốn sử dụng cho lệnh tiếp theo:"
echo "   export TOKEN='${TOKEN}'"
