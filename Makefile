# Makefile for Octop
# Usage:
#   make              - Show this help
#   make all          - Backend lint + typecheck + test (CI ship bar)
#   make build        - Build frontend + Python wheel
#   make publish      - Build + upload to PyPI
#
# Prerequisites:
#   - Node.js + npm   (frontend)
#   - Python 3.11+    (backend)
#   - uv              (recommended) or pip
#   - twine           (publish: pip install twine / make install-tools)

SHELL := /bin/bash
.DEFAULT_GOAL := help

REPO_ROOT     := $(shell pwd)
DASHBOARD_DIR := $(REPO_ROOT)/dashboard
DASHBOARD_DEST := $(REPO_ROOT)/src/octop/dashboard
DIST_DIR      := $(REPO_ROOT)/dist

# PyPI repository (override: make publish PYPI_REPO=testpypi)
PYPI_REPO  ?= pypi
PYPI_TOKEN ?=

# Prefer uv when available; fall back to plain commands (CI / pip install -e ".[dev]")
UV   := $(shell command -v uv 2>/dev/null)
RUN  := $(if $(UV),uv run,)
PYTHON := $(if $(UV),uv run python,python3)
PIP  := $(if $(UV),uv pip,python3 -m pip)

# ─── Help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "Octop Build System"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Build targets:"
	@echo "  build            Build frontend + Python wheel (full package)"
	@echo "  build-frontend   Build React dashboard only → $(DASHBOARD_DEST)"
	@echo "  build-wheel      Build Python wheel only (assumes frontend built)"
	@echo ""
	@echo "Publish targets:"
	@echo "  publish          Build + upload to PyPI (PYPI_TOKEN or prompt)"
	@echo "  publish-test     Build + upload to TestPyPI"
	@echo ""
	@echo "Development targets:"
	@echo "  dev              Start frontend + backend dev servers"
	@echo "  dev-frontend     Start Vite dev server only"
	@echo "  dev-backend      Start octop run only"
	@echo ""
	@echo "Online-deps targets (local Octop source + PyPI harness components):"
	@echo "  install-online   Create .venv-online: Octop editable + harness-* from PyPI"
	@echo "  test-online      pytest against .venv-online (not live)"
	@echo "  run-online       Start octop run from .venv-online"
	@echo ""
	@echo "Quality targets (backend — CI ship bar):"
	@echo "  all              lint + typecheck + test (backend)"
	@echo "  lint             Ruff check + format check (src, tests)"
	@echo "  format           Ruff auto-fix + format (src, tests)"
	@echo "  typecheck        mypy --strict src/octop"
	@echo "  test             pytest -m \"not live\""
	@echo "  test-live        pytest -m live"
	@echo ""
	@echo "Quality targets (frontend):"
	@echo "  lint-frontend    ESLint + Prettier check"
	@echo "  format-frontend  Prettier write"
	@echo "  typecheck-frontend  tsc --noEmit"
	@echo ""
	@echo "Quality targets (full stack):"
	@echo "  lint-all         lint + lint-frontend"
	@echo "  format-all       format + format-frontend"
	@echo "  typecheck-all    typecheck + typecheck-frontend"
	@echo "  check-all        lint-all + typecheck-all + test"
	@echo ""
	@echo "Utility targets:"
	@echo "  install          Install Python dev dependencies (alias: install-dev)"
	@echo "  install-dev      uv sync / pip install -e \".[dev]\""
	@echo "  install-tools    Install build + twine for publishing"
	@echo "  docs-cli         Regenerate docs/cli.md from Click commands"
	@echo "  clean            Remove build artifacts and caches"
	@echo "  clean-online     Remove the .venv-online environment"
	@echo "  version          Show current project version"

# ─── Build ───────────────────────────────────────────────────────────────────

.PHONY: build
build: build-frontend build-wheel

.PHONY: build-frontend
build-frontend:
	@echo "[build-frontend] Installing npm dependencies..."
	cd $(DASHBOARD_DIR) && npm ci
	@echo "[build-frontend] Building dashboard (output: $(DASHBOARD_DEST))..."
	cd $(DASHBOARD_DIR) && NODE_ENV=production NODE_OPTIONS="--max-old-space-size=2048" npm run build
	@echo "[build-frontend] Done."

.PHONY: build-wheel
build-wheel:
	@echo "[build-wheel] Generating README.pypi.md (CHANGELOG + README)..."
	@{ cat $(REPO_ROOT)/CHANGELOG.md; echo; cat $(REPO_ROOT)/README.md; } > $(REPO_ROOT)/README.pypi.md
	@cp $(REPO_ROOT)/pyproject.toml $(REPO_ROOT)/pyproject.toml.bak
	@$(PYTHON) -c "from pathlib import Path; p=Path('$(REPO_ROOT)/pyproject.toml'); p.write_text(p.read_text().replace('readme = \"README.md\"', 'readme = \"README.pypi.md\"', 1))"
	@echo "[build-wheel] Cleaning previous build artifacts..."
	rm -rf $(DIST_DIR)/*
	rm -rf $(REPO_ROOT)/build
	@echo "[build-wheel] Building wheel + sdist..."
	@set -e; \
	status=0; \
	if [ -n "$(UV)" ]; then \
		uv build --out-dir $(DIST_DIR) . || status=$$?; \
	else \
		$(PIP) install --quiet build; \
		$(PYTHON) -m build --no-isolation --outdir $(DIST_DIR) . || status=$$?; \
	fi; \
	mv $(REPO_ROOT)/pyproject.toml.bak $(REPO_ROOT)/pyproject.toml; \
	rm -f $(REPO_ROOT)/README.pypi.md; \
	exit $$status
	@echo "[build-wheel] Done. Artifacts in: $(DIST_DIR)/"
	@ls -lh $(DIST_DIR)/

# ─── Publish ─────────────────────────────────────────────────────────────────

.PHONY: publish
publish: build
	@echo "[publish] Uploading to $(PYPI_REPO)..."
	@if ! command -v twine > /dev/null 2>&1; then \
		echo "[publish] twine not found. Installing..."; \
		$(PIP) install --quiet twine; \
	fi
	@_token="$(PYPI_TOKEN)"; \
	if [ -z "$$_token" ]; then \
		echo ""; \
		printf "  PYPI_TOKEN is not set. Enter your PyPI API token (pypi-xxx): "; \
		read -r _token; \
		if [ -z "$$_token" ]; then \
			echo "[publish] No token provided. Aborting."; \
			exit 1; \
		fi; \
	fi; \
	$(if $(UV),uv run,) twine upload \
		$(if $(filter testpypi,$(PYPI_REPO)),--repository testpypi,) \
		--username __token__ --password "$$_token" \
		$(DIST_DIR)/*
	@echo "[publish] Upload complete."

.PHONY: publish-test
publish-test:
	$(MAKE) publish PYPI_REPO=testpypi

# ─── Development ─────────────────────────────────────────────────────────────

.PHONY: dev
dev:
	@echo "[dev] Starting frontend and backend dev servers (Ctrl-C to stop both)..."
	@trap 'kill 0' SIGINT; \
	(cd $(DASHBOARD_DIR) && npm run dev) & \
	($(RUN) octop run) & \
	wait

.PHONY: dev-frontend
dev-frontend:
	cd $(DASHBOARD_DIR) && npm run dev

.PHONY: dev-backend
dev-backend:
	$(RUN) octop run

# ─── Online-deps dev (local Octop source + PyPI harness components) ───────────
# Keeps a dedicated .venv-online alongside .venv. Octop itself is installed
# editable (-e) so source edits are live; the harness-* siblings are pulled
# from PyPI (--no-sources ignores the editable local paths in uv.lock).
# Re-run install-online only when a dependency version changes.
VENV_ONLINE := $(REPO_ROOT)/.venv-online
PY_ONLINE   := $(VENV_ONLINE)/bin

.PHONY: install-online
install-online:
	@echo "[install-online] Creating $(VENV_ONLINE) (local Octop + PyPI harness deps)..."
	uv venv $(VENV_ONLINE) --python 3.12
	uv pip install --no-sources --python $(PY_ONLINE)/python -e ".[dev]"
	@echo "[install-online] Done. Octop=editable(local), harness-*=PyPI."

.PHONY: test-online
test-online:
	@echo "[test-online] pytest against $(VENV_ONLINE) (not live)..."
	$(PY_ONLINE)/pytest -m "not live"

.PHONY: run-online
run-online:
	$(PY_ONLINE)/octop run

# ─── Quality (backend) ───────────────────────────────────────────────────────

.PHONY: all
all: lint typecheck test

.PHONY: lint
lint:
	@echo "[lint] Ruff check..."
	$(RUN) ruff check src tests
	@echo "[lint] Ruff format check..."
	$(RUN) ruff format --check src tests

.PHONY: format
format:
	@echo "[format] Ruff fix + format..."
	$(RUN) ruff check --fix src tests
	$(RUN) ruff format src tests

.PHONY: typecheck
typecheck:
	@echo "[typecheck] mypy..."
	$(RUN) mypy src/octop

.PHONY: test
test:
	@echo "[test] pytest (not live)..."
	$(RUN) pytest -m "not live"

.PHONY: test-live
test-live:
	@echo "[test] pytest (live)..."
	$(RUN) pytest -m live

# ─── Quality (frontend) ──────────────────────────────────────────────────────

.PHONY: lint-frontend
lint-frontend:
	@echo "[lint-frontend] ESLint..."
	cd $(DASHBOARD_DIR) && npm run lint
	@echo "[lint-frontend] Prettier check..."
	cd $(DASHBOARD_DIR) && npm run format:check

.PHONY: format-frontend
format-frontend:
	@echo "[format-frontend] Prettier..."
	cd $(DASHBOARD_DIR) && npm run format

.PHONY: typecheck-frontend
typecheck-frontend:
	@echo "[typecheck-frontend] tsc..."
	cd $(DASHBOARD_DIR) && npx tsc --noEmit

# ─── Quality (full stack) ────────────────────────────────────────────────────

.PHONY: lint-all
lint-all: lint lint-frontend

.PHONY: format-all
format-all: format format-frontend

.PHONY: typecheck-all
typecheck-all: typecheck typecheck-frontend

.PHONY: check-all
check-all: lint-all typecheck-all test

# ─── Utilities ───────────────────────────────────────────────────────────────

.PHONY: install install-dev
install install-dev:
	@echo "[install] Installing Python dev dependencies..."
ifdef UV
	uv sync
else
	$(PIP) install -e ".[dev]"
endif

.PHONY: install-tools
install-tools:
	$(PIP) install --quiet build twine
	@echo "[install-tools] build and twine installed."

.PHONY: docs-cli
docs-cli:
	@$(PYTHON) scripts/regen_cli_docs.py

.PHONY: clean
clean:
	@echo "[clean] Removing build artifacts..."
	rm -rf $(DIST_DIR)/*
	rm -rf $(DASHBOARD_DIR)/dist
	rm -rf $(REPO_ROOT)/build
	rm -rf $(REPO_ROOT)/*.egg-info
	rm -rf $(REPO_ROOT)/src/*.egg-info
	rm -rf $(REPO_ROOT)/.mypy_cache $(REPO_ROOT)/.ruff_cache $(REPO_ROOT)/.pytest_cache
	rm -rf $(REPO_ROOT)/htmlcov
	find $(REPO_ROOT)/src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "[clean] Done."

.PHONY: clean-online
clean-online:
	@echo "[clean-online] Removing $(VENV_ONLINE)..."
	rm -rf $(VENV_ONLINE)
	@echo "[clean-online] Done."

.PHONY: version
version:
	@$(PYTHON) -c "import pathlib, re; t = pathlib.Path('pyproject.toml').read_text(); m = re.search(r'^version\\s*=\\s*\"([^\"]+)\"', t, re.M); print(m.group(1) if m else 'unknown')"
