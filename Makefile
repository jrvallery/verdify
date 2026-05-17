# Verdify — Development Commands
# Usage: make <target>
SHELL := /bin/bash
VENV := /srv/greenhouse/.venv
PYTHON := $(VENV)/bin/python
PYTEST := $(PYTHON) -m pytest
RUFF := $(VENV)/bin/ruff
ESPHOME := $(VENV)/bin/esphome
ESP32_DEVICE ?= 192.168.10.111
QUIET_MINUTES ?= 30
FIRMWARE_ESPHOME := scripts/firmware-esphome-worktree.sh
FIRMWARE_OTA_BIN := firmware/.esphome/build/greenhouse/.pioenvs/greenhouse/firmware.ota.bin
REPLAY_CORPUS_GZ := firmware/test/data/replay_overrides.csv.gz
REPLAY_CORPUS_TMP ?= /tmp/verdify-replay-overrides.csv
HERMES_IRIS_RUNTIME_DIR ?= /var/lib/verdify/hermes/iris
HERMES_IRIS_ENV_FILE ?= /etc/verdify/hermes-iris.env

.PHONY: help test lint format check lighting-audit-static lighting-audit-current lighting-audit-live lighting-audit-complete firmware-check firmware-check-worktree firmware-check-all firmware-invariants firmware-replay firmware-replay-worktree firmware-dwell-preview firmware-deploy firmware-archive-artifacts firmware-promote-last-good smoke hermes-deploy-config hermes-restart hermes-smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Quality ─────────────────────────────────────────────────────────

lint: ## Run ruff linter on all Python files
	$(RUFF) check ingestor/ api/ mcp/ scripts/*.py tests/ verdify_schemas/

format: ## Auto-format Python files with ruff
	$(RUFF) format ingestor/ api/ mcp/ scripts/*.py tests/ verdify_schemas/
	$(RUFF) check --fix ingestor/ api/ mcp/ scripts/*.py tests/ verdify_schemas/

check: lint test lighting-audit-static test-firmware firmware-check ## Run all checks (lint + test + lighting audit + native firmware tests + firmware compile)
	@echo ""
	@echo "✓ All checks passed"

lighting-audit-static: ## Static lighting automation prompt-to-artifact audit
	$(PYTHON) scripts/audit-lighting-automation.py --static-only

lighting-audit-current: ## Live lighting audit; allow known OTA/post-OTA blocked status
	$(PYTHON) scripts/audit-lighting-automation.py --live --allow-blocked

lighting-audit-live: ## Strict live lighting audit; fails until OTA/post-OTA proof is complete
	$(PYTHON) scripts/audit-lighting-automation.py --live

lighting-audit-complete: ## Final lighting audit; requires OTA/post-OTA proof with no blockers
	$(PYTHON) scripts/audit-lighting-automation.py --live --require-ota

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
	gzip -cd $(REPLAY_CORPUS_GZ) > $(REPLAY_CORPUS_TMP)
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_overrides test/replay_overrides.cpp
	./firmware/test/replay_overrides $(REPLAY_CORPUS_TMP) | tail -30

test-replay-overrides: ## Validate evaluate_overrides() against full history + synthetic self-test (OBS-1e)
	bash scripts/export-replay-overrides.sh
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_overrides test/replay_overrides.cpp && ./test/replay_overrides test/data/replay_overrides.csv

firmware-invariants: ## Phase-0: run 15 invariants from invariants.h against the replay corpus (pass = bulletproof gate green)
	gzip -cd $(REPLAY_CORPUS_GZ) > $(REPLAY_CORPUS_TMP)
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_invariants test/replay_invariants.cpp
	./firmware/test/replay_invariants $(REPLAY_CORPUS_TMP)

firmware-replay: ## Phase-0: dual-ref diff of firmware mode/relay decisions between OLD and NEW git refs
	@if [ -z "$(OLD)" ] || [ -z "$(NEW)" ]; then \
	    echo "Usage: make firmware-replay OLD=<ref> NEW=<ref>"; \
	    echo "       (e.g. OLD=HEAD~5 NEW=HEAD)"; \
	    exit 2; \
	fi
	bash scripts/firmware-replay-diff.sh "$(OLD)" "$(NEW)"

firmware-replay-worktree: ## Compare firmware behavior from OLD=<ref> against current uncommitted worktree
	bash scripts/firmware-replay-worktree-diff.sh "$(OLD)"

firmware-dwell-preview: ## Phase-2: replay corpus with dwell-gate ON vs OFF, quantify whipsaw reduction
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_emit test/replay_emit.cpp
	bash scripts/firmware-dwell-preview.sh

replay-corpus-refresh: ## Refresh the replay corpus .csv.gz from live DB + validate no regression
	@bash -c '\
		set -euo pipefail; \
		CORPUS=firmware/test/data/replay_overrides.csv.gz; \
		PREV=firmware/test/data/replay_overrides.prev.csv.gz; \
		if [ -f "$$CORPUS" ]; then cp "$$CORPUS" "$$PREV"; echo "✓ snapshot existing → $$PREV"; fi; \
		OUTDIR=firmware/test/data bash scripts/export-replay-overrides.sh 0; \
		NEW=$$(wc -l < firmware/test/data/replay_overrides.csv); \
		OLD=0; [ -f "$$PREV" ] && OLD=$$(gunzip -c "$$PREV" | wc -l); \
		echo "  previous: $$OLD rows   new: $$NEW rows"; \
		if [ "$$OLD" -gt 0 ] && [ "$$NEW" -lt $$((OLD * 95 / 100)) ]; then \
			echo "✗ new corpus < 95%% of prior — aborting, restoring previous"; \
			cp "$$PREV" "$$CORPUS"; \
			rm -f firmware/test/data/replay_overrides.csv; \
			exit 1; \
		fi'
	@echo "─── Re-running replay gate against refreshed corpus ───"
	cd firmware && g++ -std=c++17 -O2 -I lib -o test/replay_overrides test/replay_overrides.cpp
	./firmware/test/replay_overrides firmware/test/data/replay_overrides.csv | tail -30
	@gzip -f firmware/test/data/replay_overrides.csv
	@echo "✓ refreshed corpus archived at firmware/test/data/replay_overrides.csv.gz"

test-v: ## Run tests with verbose output
	$(PYTEST) tests/ -v --tb=long

# ── Firmware ────────────────────────────────────────────────────────

firmware-check: ## Compile ESP32 firmware from this git worktree (validate only, no deploy)
	$(FIRMWARE_ESPHOME) compile

firmware-check-worktree: firmware-check ## Back-compat alias; firmware-check already uses this worktree

firmware-check-all: firmware-check ## Compile firmware from the only supported deploy source
	@echo "✓ Worktree firmware config compiles"

firmware-archive-artifacts: ## Archive ESPHome build outputs for FW_VERSION=<version>; set PROMOTE_LAST_GOOD=1 to update rollback target
	@if [ -z "$(FW_VERSION)" ]; then \
	    echo "Usage: make firmware-archive-artifacts FW_VERSION=<version> [PROMOTE_LAST_GOOD=1]"; \
	    exit 2; \
	fi
	@EXTRA=""; \
	if [ "$(PROMOTE_LAST_GOOD)" = "1" ]; then EXTRA="--promote-last-good"; fi; \
	bash scripts/archive-firmware-artifacts.sh "$(FW_VERSION)" $$EXTRA

firmware-promote-last-good: ## Promote a baked archived firmware FW_VERSION=<version> to rollback target
	@if [ -z "$(FW_VERSION)" ]; then \
	    echo "Usage: make firmware-promote-last-good FW_VERSION=<archived-version>"; \
	    exit 2; \
	fi
	@SRC="firmware/artifacts/$(FW_VERSION)"; \
	if [ ! -f "$$SRC/firmware.ota.bin" ] || [ ! -f "$$SRC/metadata.env" ]; then \
	    echo "Missing archived firmware artifacts under $$SRC"; \
	    exit 1; \
	fi; \
	cp "$$SRC/firmware.ota.bin" firmware/artifacts/last-good.ota.bin; \
	printf '%s\n' "$(FW_VERSION)" > firmware/artifacts/last-good.version; \
	cp "$$SRC/metadata.env" firmware/artifacts/last-good.metadata.env; \
	DEPLOYED_AT="$$(sed -n 's/^deployed_at=//p' "$$SRC/metadata.env" | tail -1)"; \
	if [ -n "$$DEPLOYED_AT" ]; then touch -d "$$DEPLOYED_AT" firmware/artifacts/last-good.ota.bin; fi; \
	echo "✓ Promoted rollback target: $(FW_VERSION)"

site-rebuild: ## Manually rebuild verdify.ai site (watcher does this automatically on vault changes)
	bash scripts/rebuild-site.sh

site-publish-status: ## Trace Obsidian vault -> Quartz build -> nginx publish state
	bash scripts/site-publish-status.sh

site-doctor: ## Audit verdify.ai source, build output, and Grafana embeds
	$(PYTHON) scripts/site-doctor.py

site-lint: ## Run cheap launch lint for public-site content and routes
	$(PYTHON) scripts/lint_public_site.py

firmware-deploy: ## Compile + OTA deploy to ESP32 + post-deploy sensor-health sweep + auto-rollback on failure
	bash scripts/firmware-deploy-preflight.sh
	@mkdir -p firmware/artifacts
	@DIRTY="$$(git diff --quiet -- . && git diff --cached --quiet -- . || echo .dirty)"; \
	if [ -n "$$DIRTY" ] && [ "$(ALLOW_DIRTY_FIRMWARE_DEPLOY)" != "1" ]; then \
		echo "✗ Dirty firmware OTA refused. Commit/stash changes or rerun with ALLOW_DIRTY_FIRMWARE_DEPLOY=1 for an operator-approved emergency."; \
		git status --short; \
		exit 1; \
	elif [ -n "$$DIRTY" ] && { [ "$(FIRMWARE_DEPLOY_OPERATOR_SIGNOFF)" != "1" ] || [ -z "$(FIRMWARE_DEPLOY_OVERRIDE_REASON)" ]; }; then \
		echo "✗ Dirty firmware OTA override requires FIRMWARE_DEPLOY_OPERATOR_SIGNOFF=1 and FIRMWARE_DEPLOY_OVERRIDE_REASON."; \
		exit 1; \
	fi; \
	FW_VERSION="$$(date +%Y.%-m.%-d.%H%M).$$(git rev-parse --short HEAD)$$DIRTY"; \
	echo "$$FW_VERSION" > firmware/artifacts/pending-fw-version.txt; \
	echo "─── Deploying fw_version=$$FW_VERSION ───"; \
	$(FIRMWARE_ESPHOME) -s fw_version "$$FW_VERSION" compile && \
	$(FIRMWARE_ESPHOME) -s fw_version "$$FW_VERSION" upload --device "$(ESP32_DEVICE)"
	@echo ""
	@echo "Waiting 60s for ESP32 reboot + ingestor reconnect + first diagnostics cycle..."
	@sleep 60
	# FW-15 (Sprint 17): sensor-health decides whether this deploy is accepted.
	# Pass → archive the new binary and update the expected-firmware pin.
	# Rollback target stays on the prior last-good until an explicit
	# firmware-promote-last-good after the 48-hour bake.
	# Fail → flash last-good back to ESP32 via firmware-rollback.sh.
	@if bash scripts/wait-for-firmware-version.sh "$$(cat firmware/artifacts/pending-fw-version.txt)" --timeout 180 && \
		EXPECTED_FW_VERSION="$$(cat firmware/artifacts/pending-fw-version.txt)" $(MAKE) sensor-health SINCE='5 minutes'; then \
		FIRMWARE_DEPLOYED_AT="$$(date -Is)" bash scripts/archive-firmware-artifacts.sh "$$(cat firmware/artifacts/pending-fw-version.txt)" ; \
		mkdir -p /srv/verdify/state ; \
		cp firmware/artifacts/pending-fw-version.txt /srv/verdify/state/expected-firmware-version ; \
		echo "✓ Deploy accepted. Archived build outputs + promoted expected firmware pin. Rollback target unchanged while this build bakes." ; \
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
	SINCE='$(or $(SINCE),5 minutes)' EXPECTED_FW_VERSION='$(EXPECTED_FW_VERSION)' bash scripts/sensor-health-sweep.sh

greenhouse-quiet-on: ## Temporarily suppress routine greenhouse automations for recording (QUIET_MINUTES=30)
	$(PYTHON) scripts/greenhouse-quiet-mode.py enable --minutes $(QUIET_MINUTES)

greenhouse-quiet-off: ## Restore greenhouse quiet-mode setpoints now
	$(PYTHON) scripts/greenhouse-quiet-mode.py disable

greenhouse-quiet-status: ## Show recording quiet-mode status
	$(PYTHON) scripts/greenhouse-quiet-mode.py status

# ── Planner (event-driven via Iris agent) ────────────────────────────

planner-publish: ## Publish today's plan to verdify.ai
	bash scripts/publish-daily-plan.sh

planner-dry: ## Dry-run planner prompts — render every event type and assert G2/G4/G7 invariants
	@$(PYTHON) scripts/planner-dry.py

# ── Hermes ─────────────────────────────────────────────────────────

hermes-deploy-config: ## Sync versioned Hermes config/SOUL into the host runtime
	HERMES_IRIS_RUNTIME_DIR='$(HERMES_IRIS_RUNTIME_DIR)' HERMES_IRIS_ENV_FILE='$(HERMES_IRIS_ENV_FILE)' bash scripts/hermes-deploy-config.sh

hermes-restart: hermes-deploy-config ## Recreate Hermes after config changes
	docker compose --profile hermes up -d --force-recreate hermes-iris

hermes-smoke: ## Check the local Hermes gateway health endpoint
	curl -fsS http://127.0.0.1:8642/health

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
