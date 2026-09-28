#!/bin/bash
# test_document_content.sh — test preview + download cho từng định dạng

BASE_URL="http://localhost:8000/v1/documents"
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI4NWNjNWQ5OS1iODQxLTQ4MzUtYjlhYy0wNTg4MzEyYTI1NzMiLCJ0ZW5hbnRfaWQiOiIxMGVkYWYwNi1lNzZlLTRkZTUtYjE0Ni1jYjAyMGEyMzMyZmYiLCJyb2xlIjoiVEVOQU5UX0FETUlOIiwidXNlcm5hbWUiOiJ0ZW5hbnQwIiwiZXhwIjoxNzg1NzM0MjM5fQ.9yNXPet2A7Sa60NlsBOh8fNTrLS9xldDsj0d7C2tyKQ"

DOC_DOCX="f469ca48-6e91-49bb-9a6f-b0ab90200359"
DOC_PDF="78a6d9ad-e226-459f-a1b9-8a1ed477cf42"
DOC_TXT="6958ace1-189e-4574-834f-ab3cf3efc840"
DOC_MD="5ae45794-858e-4dad-ae7c-283ba1d80e0a"

mkdir -p /tmp/doc_test

echo "=================================================="
echo "1. TXT — preview (inline)"
echo "=================================================="
curl -s -D /tmp/doc_test/txt_preview_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_TXT/content?disposition=inline" \
  -o /tmp/doc_test/txt_preview.out
echo "--- Headers ---"
grep -i "content-type\|content-disposition\|HTTP" /tmp/doc_test/txt_preview_headers.txt
echo "--- Nội dung (100 ký tự đầu) ---"
head -c 100 /tmp/doc_test/txt_preview.out
echo -e "\n"

echo "=================================================="
echo "2. MD — preview (inline)"
echo "=================================================="
curl -s -D /tmp/doc_test/md_preview_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_MD/content?disposition=inline" \
  -o /tmp/doc_test/md_preview.out
echo "--- Headers ---"
grep -i "content-type\|content-disposition\|HTTP" /tmp/doc_test/md_preview_headers.txt
echo "--- Nội dung (100 ký tự đầu) ---"
head -c 100 /tmp/doc_test/md_preview.out
echo -e "\n"

echo "=================================================="
echo "3. PDF — preview (inline)"
echo "=================================================="
curl -s -D /tmp/doc_test/pdf_preview_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_PDF/content?disposition=inline" \
  -o /tmp/doc_test/pdf_preview.pdf
echo "--- Headers ---"
grep -i "content-type\|content-disposition\|HTTP" /tmp/doc_test/pdf_preview_headers.txt
echo "--- File info ---"
file /tmp/doc_test/pdf_preview.pdf
ls -la /tmp/doc_test/pdf_preview.pdf
echo ""

echo "=================================================="
echo "4. DOCX — preview (inline) -> kỳ vọng trả JSON {html: ...}"
echo "=================================================="
curl -s -D /tmp/doc_test/docx_preview_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_DOCX/content?disposition=inline" \
  -o /tmp/doc_test/docx_preview.json
echo "--- Headers ---"
grep -i "content-type\|HTTP" /tmp/doc_test/docx_preview_headers.txt
echo "--- HTML (500 ký tự đầu) ---"
jq -r .html /tmp/doc_test/docx_preview.json 2>/dev/null | head -c 500
echo -e "\n"

echo "=================================================="
echo "5. DOCX — download (attachment) -> kỳ vọng file docx thật, KHÔNG phải JSON"
echo "=================================================="
curl -s -D /tmp/doc_test/docx_download_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_DOCX/content?disposition=attachment" \
  -o /tmp/doc_test/docx_download.docx
echo "--- Headers ---"
grep -i "content-type\|content-disposition\|HTTP" /tmp/doc_test/docx_download_headers.txt
echo "--- File info ---"
file /tmp/doc_test/docx_download.docx
ls -la /tmp/doc_test/docx_download.docx

echo ""
echo "=================================================="
echo "6. PDF — download (attachment), verify filename UTF-8/khoảng trắng"
echo "=================================================="
curl -s -D /tmp/doc_test/pdf_download_headers.txt \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/$DOC_PDF/content?disposition=attachment" \
  -o /tmp/doc_test/pdf_download.pdf
echo "--- Content-Disposition header (check filename*) ---"
grep -i "content-disposition" /tmp/doc_test/pdf_download_headers.txt