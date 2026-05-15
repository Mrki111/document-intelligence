#!/usr/bin/env bash
#
# End-to-end portfolio demo:
#   1. Happy path: presigned URL -> PUT PDF -> poll -> COMPLETED
#   2. Pre-signature validation gate: invalid documentType -> 400
#   3. Post-upload HEAD revalidation: lying about contentLength -> FAILED
#
# All request/response JSON is written to docs/examples/ as numbered files.
#
# Prerequisites: curl, jq, and either:
#   - API_URL env var set, or
#   - `terraform -chdir=infra output -raw api_endpoint` working
#
# Usage:
#   ./scripts/demo.sh
#   PDF=Q4_EC.pdf DOCUMENT_TYPE=general ./scripts/demo.sh
#   API_URL=https://abc.execute-api.us-east-1.amazonaws.com ./scripts/demo.sh

set -euo pipefail

PDF="${PDF:-Q4_EC.pdf}"
DOCUMENT_TYPE="${DOCUMENT_TYPE:-general}"
OUTPUT_DIR="${OUTPUT_DIR:-docs/examples}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
POLL_MAX_TRIES="${POLL_MAX_TRIES:-24}"

resolve_api_url() {
  if [[ -n "${API_URL:-}" ]]; then
    printf '%s' "$API_URL"
    return
  fi
  if command -v terraform >/dev/null 2>&1 && [[ -d infra ]]; then
    terraform -chdir=infra output -raw api_endpoint 2>/dev/null || true
  fi
}

API_URL="$(resolve_api_url)"

for cmd in curl jq; do
  command -v "$cmd" >/dev/null || { echo "Missing required tool: $cmd" >&2; exit 1; }
done
[[ -f "$PDF" ]] || { echo "PDF not found: $PDF (override via PDF=...)" >&2; exit 1; }
[[ -n "$API_URL" ]] || { echo "API_URL not set and terraform output unavailable" >&2; exit 1; }

mkdir -p "$OUTPUT_DIR"
FILENAME="$(basename "$PDF")"
SIZE=$(wc -c < "$PDF" | tr -d ' ')

echo "API:    $API_URL"
echo "PDF:    $PDF ($SIZE bytes)"
echo "Type:   $DOCUMENT_TYPE"
echo "Output: $OUTPUT_DIR"
echo

poll_until_terminal() {
  local doc_id="$1"
  local out_file="$2"
  local response status
  for i in $(seq 1 "$POLL_MAX_TRIES"); do
    response=$(curl -fsS "$API_URL/documents/$doc_id")
    status=$(printf '%s' "$response" | jq -r '.status')
    printf '    [%02d/%02d] %s\n' "$i" "$POLL_MAX_TRIES" "$status"
    if [[ "$status" == "COMPLETED" || "$status" == "FAILED" ]]; then
      break
    fi
    sleep "$POLL_INTERVAL"
  done
  printf '%s' "$response" | jq . > "$out_file"
  echo "    saved: $out_file"
}

# ---------------- 1. Happy path ----------------
echo "=== 1. happy path ==="

UPLOAD_REQUEST=$(jq -n \
  --arg fn "$FILENAME" \
  --arg dt "$DOCUMENT_TYPE" \
  --argjson sz "$SIZE" \
  '{filename: $fn, documentType: $dt, contentType: "application/pdf", contentLength: $sz}')
echo "$UPLOAD_REQUEST" > "$OUTPUT_DIR/01_upload_url_request.json"
echo "==> POST /upload-url"

UPLOAD_RESPONSE=$(curl -fsS -X POST "$API_URL/upload-url" \
  -H "Content-Type: application/json" \
  -d "$UPLOAD_REQUEST")
printf '%s' "$UPLOAD_RESPONSE" | jq '.uploadUrl = "<presigned-url-redacted>"' > "$OUTPUT_DIR/02_upload_url_response.json"

DOC_ID=$(printf '%s' "$UPLOAD_RESPONSE" | jq -r '.documentId')
URL=$(printf '%s' "$UPLOAD_RESPONSE" | jq -r '.uploadUrl')
echo "    documentId: $DOC_ID"

echo "==> PUT $FILENAME"
curl -fsS -X PUT "$URL" -H "Content-Type: application/pdf" --upload-file "$PDF" >/dev/null
echo "    upload OK"

echo "==> Polling GET /documents/$DOC_ID"
poll_until_terminal "$DOC_ID" "$OUTPUT_DIR/03_get_document_completed.json"
echo

# ---------------- 2. Pre-signature validation gate ----------------
echo "=== 2. failure: invalid documentType (gated before URL is signed) ==="

INVALID_REQUEST='{"filename":"bad.pdf","documentType":"unknown","contentType":"application/pdf","contentLength":1024}'
printf '%s' "$INVALID_REQUEST" | jq . > "$OUTPUT_DIR/04_invalid_request.json"

INVALID_HTTP_CODE=$(curl -sS -o "$OUTPUT_DIR/05_invalid_response.json" \
  -w '%{http_code}' \
  -X POST "$API_URL/upload-url" \
  -H "Content-Type: application/json" \
  -d "$INVALID_REQUEST")
echo "    HTTP $INVALID_HTTP_CODE"
if command -v jq >/dev/null && jq . "$OUTPUT_DIR/05_invalid_response.json" >/dev/null 2>&1; then
  jq . "$OUTPUT_DIR/05_invalid_response.json" > "$OUTPUT_DIR/05_invalid_response.json.tmp"
  mv "$OUTPUT_DIR/05_invalid_response.json.tmp" "$OUTPUT_DIR/05_invalid_response.json"
fi
echo "    saved: $OUTPUT_DIR/05_invalid_response.json"
echo

# ---------------- 3. Post-upload HEAD revalidation ----------------
echo "=== 3. failure: declared contentLength does not match uploaded bytes ==="

BAD_REQUEST=$(jq -n \
  --arg fn "$FILENAME" \
  --arg dt "$DOCUMENT_TYPE" \
  '{filename: $fn, documentType: $dt, contentType: "application/pdf", contentLength: 999999}')
echo "$BAD_REQUEST" > "$OUTPUT_DIR/06_mismatched_size_request.json"

BAD_RESPONSE=$(curl -fsS -X POST "$API_URL/upload-url" \
  -H "Content-Type: application/json" \
  -d "$BAD_REQUEST")
BAD_DOC_ID=$(printf '%s' "$BAD_RESPONSE" | jq -r '.documentId')
BAD_URL=$(printf '%s' "$BAD_RESPONSE" | jq -r '.uploadUrl')
echo "    documentId: $BAD_DOC_ID (declared 999999 bytes, actual $SIZE)"

echo "==> PUT $FILENAME (S3 accepts because the presigned URL does not enforce size)"
curl -fsS -X PUT "$BAD_URL" -H "Content-Type: application/pdf" --upload-file "$PDF" >/dev/null
echo "    upload OK"

echo "==> Polling GET /documents/$BAD_DOC_ID (expect FAILED with INVALID_UPLOAD_SIZE)"
poll_until_terminal "$BAD_DOC_ID" "$OUTPUT_DIR/07_mismatched_size_final.json"
echo

# ---------------- summary ----------------
echo "=== artifacts ==="
ls -la "$OUTPUT_DIR"
