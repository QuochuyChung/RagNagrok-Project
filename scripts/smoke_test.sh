#!/usr/bin/env bash

set -Eeuo pipefail

GATEWAY_PORT="${GATEWAY_PORT:-8000}"
QDRANT_HTTP_PORT="${QDRANT_HTTP_PORT:-6333}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

check_endpoint() {
    local name="$1"
    local url="$2"

    printf "Checking %-20s " "${name}"

    curl \
        --fail \
        --silent \
        --show-error \
        --max-time 10 \
        "${url}"

    printf "\n"
}

check_endpoint \
    "Gateway health" \
    "http://localhost:${GATEWAY_PORT}/health"

check_endpoint \
    "Gateway version" \
    "http://localhost:${GATEWAY_PORT}/version"

check_endpoint \
    "Qdrant readiness" \
    "http://localhost:${QDRANT_HTTP_PORT}/readyz"

check_endpoint \
    "Ollama version" \
    "http://localhost:${OLLAMA_PORT}/api/version"

echo
echo "Sprint 1 smoke test passed."