#!/usr/bin/env bash
# =============================================================================
# load_test.sh — Simple load test for the gateway health endpoint
# =============================================================================
# Sends N concurrent requests and reports latency + error rate.
# Requires: curl, bc
#
# Usage:
#   bash scripts/load_test.sh [N_REQUESTS] [CONCURRENCY]
#   bash scripts/load_test.sh 50 10
# =============================================================================

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
N_REQUESTS="${1:-20}"
CONCURRENCY="${2:-5}"
ENDPOINT="${GATEWAY_URL}/health"

echo "════════════════════════════════════════════════"
echo "  Load Test: ${ENDPOINT}"
echo "  Requests: ${N_REQUESTS}  |  Concurrency: ${CONCURRENCY}"
echo "════════════════════════════════════════════════"

SUCCESS=0
FAILURES=0
TOTAL_LATENCY=0

run_request() {
  local start
  start=$(date +%s%N)
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${ENDPOINT}")
  local end
  end=$(date +%s%N)
  local latency_ms
  latency_ms=$(( (end - start) / 1000000 ))

  if [[ "$http_code" == "200" ]]; then
    echo "OK ${latency_ms}ms"
  else
    echo "FAIL ${http_code} ${latency_ms}ms"
  fi
}

export -f run_request
export ENDPOINT

# Use xargs for concurrency
seq "${N_REQUESTS}" | xargs -P "${CONCURRENCY}" -I {} bash -c 'run_request' | \
  awk '
    BEGIN { ok=0; fail=0; total=0 }
    /^OK/   { ok++; total+=$2 }
    /^FAIL/ { fail++ }
    END {
      printf "\n════════════════════════════════════════════════\n"
      printf "  Results\n"
      printf "  Success : %d\n", ok
      printf "  Failures: %d\n", fail
      if (ok > 0) {
        avg = total / ok
        sub(/ms/, "", avg)
        printf "  Avg Lat : %.1f ms\n", avg
      }
      printf "  Error %%  : %.1f%%\n", (fail/(ok+fail))*100
      printf "════════════════════════════════════════════════\n"
    }
  '
