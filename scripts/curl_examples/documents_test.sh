#!/usr/bin/env bash
#
# scripts/curl_examples/documents_test.sh
#
# Test toàn bộ luồng document endpoints: POST /documents, GET /documents,
# DELETE /documents/{doc_id}, POST /documents/{doc_id}/restore.
#
# Yêu cầu: docker compose đang up (gateway + postgres), curl, jq đã cài.
#   sudo apt install jq   # nếu chưa có
#
# Chạy: bash scripts/curl_examples/documents_test.sh
#
set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0

# ── màu cho dễ đọc output ────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

step()   { echo -e "\n${YELLOW}== $1 ==${NC}"; }
pass()   { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS+1)); }
fail()   { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL+1)); }

# assert_eq <actual> <expected> <mô tả>
assert_eq() {
    if [[ "$1" == "$2" ]]; then
        pass "$3 (got: $1)"
    else
        fail "$3 (expected: $2, got: $1)"
    fi
}

# ── chuẩn bị file test mẫu ───────────────────────────────────────────────
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Đặt tên file theo timestamp -> mỗi lần chạy script là 1 doc_name MỚI,
# không đụng lịch sử version của lần chạy trước (do TENANT_ID hay bị tái sử dụng
# giữa các lần test thủ công, get_latest_version không lọc is_deleted nên version
# sẽ tiếp tục tăng từ lần trước nếu trùng tên file).
RUN_ID=$(date +%s)
SAMPLE_TXT="$TMP_DIR/sample_${RUN_ID}.txt"
SAMPLE_MD="$TMP_DIR/sample_${RUN_ID}.md"
echo "Đây là nội dung test cho document ingestion pipeline." > "$SAMPLE_TXT"
printf '# Test Heading\n\nNội dung markdown test.\n' > "$SAMPLE_MD"

# =============================================================================
# 0. Setup: TENANT_ID phải được truyền qua biến môi trường
#
# Endpoint POST /tenants (tạo tenant mới qua API) chưa được implement
# (route hiện tại chỉ có GET /v1/tenants/{tenant_id}), nên script không
# tự tạo tenant được. Insert tay trước:
#
#   docker exec -it <container_postgres> psql -U ragnarok -d rag_db -c \
#     "INSERT INTO tenants (tenant_name, collection_name)
#      VALUES ('test-tenant', 'test_collection') RETURNING tenant_id;"
#
# Rồi chạy:
#   TENANT_ID="<uuid-vua-insert>" bash scripts/curl_examples/documents_test.sh
# =============================================================================
step "0. Kiểm tra TENANT_ID"

if [[ -z "${TENANT_ID:-}" ]]; then
    echo -e "${RED}Thiếu biến môi trường TENANT_ID.${NC}"
    echo "Insert tenant test bằng tay trước, rồi chạy lại:"
    echo '  TENANT_ID="<uuid>" bash scripts/curl_examples/documents_test.sh'
    exit 1
fi
echo "TENANT_ID=$TENANT_ID"

# =============================================================================
# 1. POST /documents — upload lần đầu (phải tạo version 1)
# =============================================================================
step "1. Upload document lần đầu (.txt)"

RESP=$(curl -s -X POST "$BASE_URL/documents" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$SAMPLE_TXT")
echo "$RESP" | jq .

DOC_ID=$(echo "$RESP" | jq -r '.doc_id // empty')
VERSION=$(echo "$RESP" | jq -r '.doc_version // empty')

[[ -n "$DOC_ID" ]] && pass "Nhận được doc_id: $DOC_ID" || fail "Không có doc_id trong response"
assert_eq "$VERSION" "1" "Version đầu tiên phải là 1"

# =============================================================================
# 2. POST /documents — upload lại y hệt (test idempotent)
# =============================================================================
step "2. Upload lại y hệt file cũ (test idempotent)"

RESP=$(curl -s -X POST "$BASE_URL/documents" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$SAMPLE_TXT")
echo "$RESP" | jq .

# Không có field is_duplicate trong response (quyết định: trùng thì giữ nguyên,
# không cần báo cho client) -- verify duplicate bằng cách check doc_id và
# doc_version giữ y nguyên so với lần upload trước, tức là không tạo bản mới.
DUP_DOC_ID=$(echo "$RESP" | jq -r '.doc_id // empty')
DUP_VERSION=$(echo "$RESP" | jq -r '.doc_version // empty')

assert_eq "$DUP_DOC_ID" "$DOC_ID" "doc_id phải giữ nguyên (trùng nội dung -> không tạo bản mới)"
assert_eq "$DUP_VERSION" "1" "doc_version phải giữ nguyên là 1 (không tăng version)"

# =============================================================================
# 3. POST /documents — upload nội dung khác, cùng tên (test versioning)
# =============================================================================
step "3. Upload nội dung khác, cùng tên file (test tăng version)"

echo "Nội dung đã thay đổi - version 2." > "$SAMPLE_TXT"

RESP=$(curl -s -X POST "$BASE_URL/documents" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$SAMPLE_TXT")
echo "$RESP" | jq .

DOC_ID_V2=$(echo "$RESP" | jq -r '.doc_id // empty')
VERSION_V2=$(echo "$RESP" | jq -r '.doc_version // empty')

assert_eq "$VERSION_V2" "2" "Nội dung khác phải tạo version 2"
if [[ "$DOC_ID_V2" != "$DOC_ID" ]]; then
    pass "doc_id version 2 khác doc_id version 1 (đúng kỳ vọng)"
else
    fail "doc_id version 2 trùng version 1 -- không đúng"
fi

# =============================================================================
# 4. GET /documents — chỉ được thấy version mới nhất (latest wins)
# =============================================================================
step "4. List documents -- kỳ vọng chỉ ra 1 bản active (version 2)"

RESP=$(curl -s "$BASE_URL/documents" -H "X-Tenant-ID: $TENANT_ID")
echo "$RESP" | jq .

TXT_FILENAME=$(basename "$SAMPLE_TXT")
MATCHING_COUNT=$(echo "$RESP" | jq -r --arg name "$TXT_FILENAME" \
    '[.documents[] | select(.doc_name == $name)] | length')
ACTIVE_VERSION=$(echo "$RESP" | jq -r --arg name "$TXT_FILENAME" \
    '.documents[] | select(.doc_name == $name) | .doc_version')

assert_eq "$MATCHING_COUNT" "1" "Chỉ 1 bản active cho '$TXT_FILENAME' (không phải cả 2 version cùng lúc)"
assert_eq "$ACTIVE_VERSION" "2" "Bản active phải là version 2 (bản mới nhất)"

# =============================================================================
# 5. Upload file .md để test thêm 1 loại định dạng khác
# =============================================================================
step "5. Upload document .md"

RESP=$(curl -s -X POST "$BASE_URL/documents" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$SAMPLE_MD")
echo "$RESP" | jq .

MD_DOC_ID=$(echo "$RESP" | jq -r '.doc_id // empty')
[[ -n "$MD_DOC_ID" ]] && pass "Upload .md thành công: $MD_DOC_ID" || fail "Upload .md thất bại"

# =============================================================================
# 6. Upload định dạng KHÔNG hỗ trợ -- kỳ vọng lỗi 422
# =============================================================================
step "6. Upload định dạng không hỗ trợ (.exe) -- kỳ vọng 422"

BAD_FILE="$TMP_DIR/bad.exe"
echo "fake binary" > "$BAD_FILE"

HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" -X POST "$BASE_URL/documents" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$BAD_FILE")
cat /tmp/resp_body.json | jq . 2>/dev/null || cat /tmp/resp_body.json

assert_eq "$HTTP_CODE" "422" "File .exe phải bị từ chối với 422"

# =============================================================================
# 7. Request thiếu X-Tenant-ID -- kỳ vọng 400
# =============================================================================
step "7. GET /documents không có header X-Tenant-ID -- kỳ vọng 400"

HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" "$BASE_URL/documents")
cat /tmp/resp_body.json | jq .

assert_eq "$HTTP_CODE" "400" "Thiếu X-Tenant-ID phải trả 400"

# =============================================================================
# 8. Request với tenant không tồn tại -- kỳ vọng 404
# =============================================================================
step "8. GET /documents với tenant giả -- kỳ vọng 404"

FAKE_TENANT="00000000-0000-0000-0000-000000000000"
HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" "$BASE_URL/documents" \
    -H "X-Tenant-ID: $FAKE_TENANT")
cat /tmp/resp_body.json | jq .

assert_eq "$HTTP_CODE" "404" "Tenant không tồn tại phải trả 404"

# =============================================================================
# 9. DELETE /documents/{doc_id} -- soft delete
# =============================================================================
step "9. Soft-delete document version 2"

HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" -X DELETE \
    "$BASE_URL/documents/$DOC_ID_V2" \
    -H "X-Tenant-ID: $TENANT_ID")
cat /tmp/resp_body.json | jq .

assert_eq "$HTTP_CODE" "200" "Soft-delete thành công phải trả 200"

# =============================================================================
# 10. GET /documents sau khi xóa -- document đã xóa không được xuất hiện
# =============================================================================
step "10. List lại -- document vừa xóa không còn trong danh sách active"

RESP=$(curl -s "$BASE_URL/documents" -H "X-Tenant-ID: $TENANT_ID")
echo "$RESP" | jq .

STILL_THERE=$(echo "$RESP" | jq -r --arg id "$DOC_ID_V2" \
    '.documents[] | select(.doc_id == $id) | .doc_id // empty')

if [[ -z "$STILL_THERE" ]]; then
    pass "Document đã xóa không còn xuất hiện trong list"
else
    fail "Document đã xóa VẪN xuất hiện trong list -- soft delete lỗi"
fi

# =============================================================================
# 11. DELETE lần 2 -- doc_id không tồn tại (đã xóa rồi) -- kỳ vọng 404
# =============================================================================
step "11. Xóa lại document đã xóa -- kỳ vọng 404"

HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" -X DELETE \
    "$BASE_URL/documents/$DOC_ID_V2" \
    -H "X-Tenant-ID: $TENANT_ID")
cat /tmp/resp_body.json | jq .

assert_eq "$HTTP_CODE" "404" "Xóa document đã xóa rồi phải trả 404"

# =============================================================================
# 12. [TẠM BỎ QUA] Restore chưa được tích hợp vào code, bỏ test này lại sau.
# =============================================================================

# =============================================================================
# 13. DELETE với doc_id không tồn tại (UUID random) -- kỳ vọng 404
# =============================================================================
step "13. Xóa doc_id ngẫu nhiên không tồn tại -- kỳ vọng 404"

RANDOM_UUID="11111111-1111-1111-1111-111111111111"
HTTP_CODE=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" -X DELETE \
    "$BASE_URL/documents/$RANDOM_UUID" \
    -H "X-Tenant-ID: $TENANT_ID")
cat /tmp/resp_body.json | jq .

assert_eq "$HTTP_CODE" "404" "doc_id không tồn tại phải trả 404"

# =============================================================================
# Tổng kết
# =============================================================================
echo -e "\n=========================================="
echo -e "${GREEN}PASS: $PASS${NC}   ${RED}FAIL: $FAIL${NC}"
echo -e "==========================================\n"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0