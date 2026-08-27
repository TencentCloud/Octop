# Standalone Makefile for green portable packaging.
# Does not modify the repo-root Makefile — merge-friendly with upstream.
#
# Usage (from repo root):
#   make -f desktop/portable/Makefile green
#   make -f desktop/portable/Makefile green GREEN_PLAT=linux-amd64
#   make -f desktop/portable/Makefile green-linux
#   make -f desktop/portable/Makefile clean

SHELL := /bin/bash
REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
GREEN_PLAT ?=

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "Green portable (offline zip)"
	@echo "  make -f desktop/portable/Makefile green              # host plat zip"
	@echo "  make -f desktop/portable/Makefile green GREEN_PLAT=…"
	@echo "  make -f desktop/portable/Makefile bootstrap|wheels|package|green-linux|clean"

.PHONY: bootstrap
bootstrap:
	bash $(REPO_ROOT)/desktop/portable/bootstrap-runtime.sh $(GREEN_PLAT)

.PHONY: wheels
wheels:
	bash $(REPO_ROOT)/desktop/portable/vendor-wheels.sh $(GREEN_PLAT)

.PHONY: package
package:
	bash $(REPO_ROOT)/desktop/portable/package.sh $(GREEN_PLAT)

.PHONY: green
green:
	$(MAKE) -C $(REPO_ROOT) build-frontend
	bash $(REPO_ROOT)/desktop/portable/bootstrap-runtime.sh $(GREEN_PLAT)
	bash $(REPO_ROOT)/desktop/portable/package.sh $(GREEN_PLAT)
	@echo "[green] Done. Zips under $(REPO_ROOT)/desktop/portable/release/"

.PHONY: green-linux
green-linux:
	$(MAKE) -C $(REPO_ROOT) build-frontend
	bash $(REPO_ROOT)/desktop/portable/package-linux-docker.sh $(if $(GREEN_PLAT),$(GREEN_PLAT),linux-amd64)

.PHONY: clean
clean:
	rm -rf $(REPO_ROOT)/desktop/portable/runtimes \
		$(REPO_ROOT)/desktop/portable/wheels \
		$(REPO_ROOT)/desktop/portable/.cache \
		$(REPO_ROOT)/desktop/portable/release
	rm -f $(REPO_ROOT)/desktop/portable/requirements-*.txt \
		$(REPO_ROOT)/desktop/portable/overrides-*.txt
	@echo "[green] removed generated files under $(REPO_ROOT)/desktop/portable"
