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

test-firmware: ## Run native C++ logic tests + replay against golden CSV (same code as ESP32)
	cd firmware && g++ -std=c++17 -I lib -o test/test_greenhouse test/test_greenhouse_logic.cpp && ./test/test_greenhouse
	# OBS-1e (Sprint 16) — replay validation against 8 months of real telemetry.
	# Required gate per CLAUDE.md Firmware Change Protocol: unit tests alone
	# cannot catch structural flag regressions (e.g. the shipped-and-caught
	# vpd_dry_override dead code in commit 82b18ad → patched in caa2cea).
	test -f firmware/test/data/replay_overrides.csv \
	  || gunzip -k firmware/test/data/replay_overrides.csv.gz
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_overrides test/replay_overrides.cpp
	./firmware/test/replay_overrides firmware/test/data/replay_overrides.csv | tail -30

test-replay: ## Run historical replay simulation (export + simulate)
	bash scripts/export-replay-data.sh 10
	cd firmware && g++ -std=c++17 -I lib -o test/replay_harness test/replay_harness.cpp && ./test/replay_harness test/data/replay_data.csv

test-replay-overrides: ## Validate evaluate_overrides() against full history + synthetic self-test (OBS-1e)
	bash scripts/export-replay-overrides.sh
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_overrides test/replay_overrides.cpp && ./test/replay_overrides test/data/replay_overrides.csv

test-v: ## Run tests with verbose output
	$(PYTEST) tests/ -v --tb=long

# ── Firmware ────────────────────────────────────────────────────────

firmware-check: ## Compile ESP32 firmware (validate only, no deploy)
	cd /srv/greenhouse/esphome && $(ESPHOME) compile greenhouse.yaml

site-rebuild: ## Manually rebuild verdify.ai site (watcher does this automatically on vault changes)
	bash scripts/rebuild-site.sh

firmware-deploy: ## Compile + OTA deploy to ESP32 + post-deploy sensor-health sweep + auto-rollback on failure
	@mkdir -p firmware/artifacts
	cd /srv/greenhouse/esphome && $(ESPHOME) compile greenhouse.yaml
	cd /srv/greenhouse/esphome && $(ESPHOME) upload --device 192.168.10.111 greenhouse.yaml
	@echo ""
	@echo "Waiting 60s for ESP32 reboot + ingestor reconnect + first diagnostics cycle..."
	@sleep 60
	# FW-15 (Sprint 17): sensor-health decides whether this deploy is accepted.
	# Pass → promote new binary to last-good (rollback target for next deploy).
	# Fail → flash last-good back to ESP32 via firmware-rollback.sh.
	@if $(MAKE) sensor-health SINCE='5 minutes'; then \
		cp /srv/greenhouse/esphome/.esphome/build/greenhouse/.pioenvs/greenhouse/firmware.ota.bin firmware/artifacts/last-good.ota.bin ; \
		echo "✓ Deploy accepted. Promoted new binary to firmware/artifacts/last-good.ota.bin (rollback target for next deploy)." ; \
	else \
		echo "" ; \
		echo "▓▓▓  SENSOR-HEALTH FAILED POST-OTA  —  initiating auto-rollback  ▓▓▓" ; \
		bash scripts/firmware-rollback.sh firmware/artifacts/last-good.ota.bin ; \
		echo "" ; \
		echo "Waiting 60s for ESP32 to reboot onto rolled-back firmware..." ; \
		sleep 60 ; \
		echo "Re-running sensor-health against rolled-back firmware:" ; \
		$(MAKE) sensor-health SINCE='5 minutes' ; \
		exit 1 ; \
	fi

firmware-rollback: ## Manually flash the saved last-good.ota.bin back onto the ESP32
	bash scripts/firmware-rollback.sh firmware/artifacts/last-good.ota.bin

sensor-health: ## Run sensor health sweep (layer 3 of Firmware Change Protocol)
	SINCE='$(or $(SINCE),5 minutes)' bash scripts/sensor-health-sweep.sh

# ── Planner (event-driven via Iris agent) ────────────────────────────

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
