# Makefile for octop-harness
# Usage:
#   make              - Show this help
#   make all          - format + lint + typecheck + test (ship bar)
#   make build        - Build Python wheel + sdist
#   make publish      - Build + upload to PyPI
#
# Prerequisites:
#   - Python 3.12+
#   - uv              (recommended) or pip
#   - twine           (publish: pip install twine / make install-tools)

SHELL := /bin/bash
.DEFAULT_GOAL := help

REPO_ROOT := $(shell pwd)
DIST_DIR  := $(REPO_ROOT)/dist

PYPI_REPO  ?= pypi
PYPI_TOKEN ?=

UV     := $(shell command -v uv 2>/dev/null)
RUN    := $(if $(UV),uv run,)
PYTHON := $(if $(UV),uv run python,python3)
PIP    := $(if $(UV),uv pip,python3 -m pip)

# ─── Help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "octop-harness Build System"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Build targets:"
	@echo "  build            Build Python wheel + sdist"
	@echo ""
	@echo "Publish targets:"
	@echo "  publish          Build + upload to PyPI (PYPI_TOKEN or prompt)"
	@echo "  publish-test     Build + upload to TestPyPI"
	@echo ""
	@echo "Quality targets (ship bar):"
	@echo "  all              format + lint + typecheck + test"
	@echo "  lint             Ruff check + format check (src, tests)"
	@echo "  format           Ruff auto-fix + format (src, tests)"
	@echo "  typecheck        mypy --strict src"
	@echo "  test             pytest with coverage"
	@echo ""
	@echo "Utility targets:"
	@echo "  install-hooks    Point git to .githooks (pre-commit: make all)"
	@echo "  install          Install Python dev dependencies (alias: install-dev)"
	@echo "  install-dev      uv sync --group dev / pip install -e \".[dev]\""
	@echo "  install-tools    Install build + twine for publishing"
	@echo "  clean            Remove build artifacts and caches"
	@echo "  version          Show current project version"

# ─── Build ───────────────────────────────────────────────────────────────────

.PHONY: build
build:
	@echo "[build] Cleaning previous build artifacts..."
	rm -rf $(DIST_DIR)/*
	rm -rf $(REPO_ROOT)/build
	@echo "[build] Building wheel + sdist..."
ifdef UV
	uv build --out-dir $(DIST_DIR) .
else
	$(PIP) install --quiet build
	$(PYTHON) -m build --no-isolation --outdir $(DIST_DIR) .
endif
	@echo "[build] Done. Artifacts in: $(DIST_DIR)/"
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

# ─── Quality ─────────────────────────────────────────────────────────────────

.PHONY: all
all: format lint typecheck test

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
	$(RUN) mypy src

.PHONY: test
test:
	@echo "[test] pytest..."
	$(RUN) pytest --cov=octop_harness --cov-report=term-missing

# ─── Utilities ───────────────────────────────────────────────────────────────

.PHONY: install-hooks
install-hooks:
	@echo "[install-hooks] Setting core.hooksPath=.githooks"
	git config core.hooksPath .githooks
	@chmod +x "$(REPO_ROOT)/.githooks/"* 2>/dev/null || true
	@echo "[install-hooks] Done. Pre-commit will run: make all (format + lint + typecheck + test)"
	@echo "[install-hooks] Bypass: SKIP_PRECOMMIT=1 git commit …   or   git commit --no-verify"

.PHONY: install install-dev
install install-dev:
	@echo "[install] Installing Python dev dependencies..."
ifdef UV
	uv sync --group dev
else
	$(PIP) install -e ".[dev]"
endif

.PHONY: install-tools
install-tools:
	$(PIP) install --quiet build twine
	@echo "[install-tools] build and twine installed."

.PHONY: clean
clean:
	@echo "[clean] Removing build artifacts..."
	rm -rf $(DIST_DIR)/*
	rm -rf $(REPO_ROOT)/build
	rm -rf $(REPO_ROOT)/*.egg-info
	rm -rf $(REPO_ROOT)/src/*.egg-info
	rm -rf $(REPO_ROOT)/.mypy_cache $(REPO_ROOT)/.ruff_cache $(REPO_ROOT)/.pytest_cache
	rm -rf $(REPO_ROOT)/htmlcov $(REPO_ROOT)/.coverage $(REPO_ROOT)/coverage.xml
	find $(REPO_ROOT)/src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "[clean] Done."

.PHONY: version
version:
	@$(PYTHON) -c "from octop_harness._version import __version__; print(__version__)"
