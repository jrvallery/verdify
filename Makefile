# Verdify — Development Commands
# Usage: make <target>
SHELL := /bin/bash
VENV := /srv/greenhouse/.venv
PYTHON := $(VENV)/bin/python
PYTEST := $(PYTHON) -m pytest
RUFF := $(VENV)/bin/ruff
ESPHOME := $(VENV)/bin/esphome

.PHONY: help test lint format check firmware-check smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Quality ─────────────────────────────────────────────────────────

lint: ## Run ruff linter on all Python files
	$(RUFF) check ingestor/ api/ scripts/*.py tests/

format: ## Auto-format Python files with ruff
	$(RUFF) format ingestor/ api/ scripts/*.py tests/
	$(RUFF) check --fix ingestor/ api/ scripts/*.py tests/

check: lint test test-firmware firmware-check ## Run all checks (lint + test + native firmware tests + firmware compile)
	@echo ""
	@echo "✓ All checks passed"

# ── Testing ─────────────────────────────────────────────────────────

test: ## Run full smoke test suite against live stack
	$(PYTEST) tests/

test-fast: ## Run tests excluding slow planner tests
	$(PYTEST) tests/ -k "not Planner and not Context"

test-firmware: ## Run native C++ logic tests (same code as ESP32)
	cd firmware && g++ -std=c++17 -I lib -o test/test_greenhouse test/test_greenhouse_logic.cpp && ./test/test_greenhouse

test-replay: ## Run historical replay simulation (export + simulate)
	bash scripts/export-replay-data.sh 10
	cd firmware && g++ -std=c++17 -I lib -o test/replay_harness test/replay_harness.cpp && ./test/replay_harness test/data/replay_data.csv

test-v: ## Run tests with verbose output
	$(PYTEST) tests/ -v --tb=long

# ── Firmware ────────────────────────────────────────────────────────

firmware-check: ## Compile ESP32 firmware (validate only, no deploy)
	cd /srv/greenhouse/esphome && $(ESPHOME) compile greenhouse-v2.yaml

firmware-deploy: ## Compile + OTA deploy to ESP32
	cd /srv/greenhouse/esphome && $(ESPHOME) compile greenhouse-v2.yaml
	cd /srv/greenhouse/esphome && $(ESPHOME) upload --device 192.168.10.111 greenhouse-v2.yaml

# ── Planner ─────────────────────────────────────────────────────────

planner-dry: ## Render planner prompt (no API call)
	$(PYTHON) scripts/planner.py --dry-run 2>/dev/null

planner-run: ## Run a live planning cycle
	$(PYTHON) scripts/planner.py

planner-publish: ## Publish today's plan to verdify.ai
	bash scripts/publish-daily-plan.sh

# ── Stack ───────────────────────────────────────────────────────────

up: ## Start all Docker services
	docker compose up -d

down: ## Stop all Docker services
	docker compose down

ps: ## Show running containers
	docker compose ps

logs: ## Tail all container logs
	docker compose logs -f --tail=50

ingestor-restart: ## Restart the ingestor service
	sudo systemctl restart verdify-ingestor
	systemctl status verdify-ingestor --no-pager | head -5

ingestor-logs: ## Tail ingestor logs
	journalctl -u verdify-ingestor -f

# ── Database ────────────────────────────────────────────────────────

db-shell: ## Open psql shell
	docker exec -it verdify-timescaledb psql -U verdify -d verdify

db-dump: ## Dump schema to db/schema.sql
	docker exec verdify-timescaledb pg_dump -U verdify -d verdify --schema-only > db/schema.sql

db-scorecard: ## Show today's planner scorecard
	docker exec verdify-timescaledb psql -U verdify -d verdify -c "SELECT * FROM fn_planner_scorecard(CURRENT_DATE);"

# ── Cleanup ─────────────────────────────────────────────────────────

clean: ## Remove Python bytecode and pytest cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
