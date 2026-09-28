# ─────────────────────────────────────────────────────────────────────────────
# Ragnarok — Multi-Tenant RAG API Gateway
# Makefile for common development tasks
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help up down build logs ps restart shell test lint format clean

COMPOSE = docker compose
SERVICE = gateway

## help: Show available targets
help:
	@echo ""
	@echo "  Ragnarok — Multi-Tenant RAG Gateway"
	@echo "  ─────────────────────────────────────"
	@grep -E '^## ' Makefile | sed 's/## /  /'
	@echo ""

## up: Start all services in detached mode
up:
	$(COMPOSE) up -d

## up-build: Rebuild images and start all services
up-build:
	$(COMPOSE) up -d --build

## down: Stop and remove all containers
down:
	$(COMPOSE) down

## down-v: Stop and remove all containers AND volumes (⚠ destroys data)
down-v:
	$(COMPOSE) down -v

## build: Build the gateway Docker image
build:
	$(COMPOSE) build $(SERVICE)

## logs: Follow logs for all services (Ctrl-C to exit)
logs:
	$(COMPOSE) logs -f

## logs-gateway: Follow gateway logs only
logs-gateway:
	$(COMPOSE) logs -f $(SERVICE)

## ps: List running containers
ps:
	$(COMPOSE) ps

## restart: Restart the gateway service
restart:
	$(COMPOSE) restart $(SERVICE)

## shell: Open a bash shell inside the gateway container
shell:
	$(COMPOSE) exec $(SERVICE) /bin/bash

## health: Check gateway health endpoint
health:
	curl -s http://localhost:8000/health | python -m json.tool

## health-debug: Check gateway health with per-service breakdown
health-debug:
	curl -s "http://localhost:8000/health?debug=true" | python -m json.tool

## version: Check gateway version endpoint
version:
	curl -s http://localhost:8000/version | python -m json.tool

## test: Run unit tests
test:
	$(COMPOSE) exec $(SERVICE) python -m pytest tests/unit -v

## test-integration: Run integration tests (requires full stack)
test-integration:
	$(COMPOSE) exec $(SERVICE) python -m pytest tests/integration -v

## lint: Run ruff linter
lint:
	ruff check app/ tests/

## format: Format code with ruff
format:
	ruff format app/ tests/

## clean: Remove Python cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
