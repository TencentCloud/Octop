# Local verification: Team members created by another runtime

The screenshot renders actual saved local pytest summaries. It is automated test evidence, not a product UI demonstration or a human-review attestation. Contributor review and hosted CI remain separate.

- Base: `44c22434b090cb78d3a4a2d6fad786e7bbc95863`.
- Tested source blob: `267fe2ddebe105875abcb385a06874e26199c5d0` (`src/octop/infra/agents/manager.py`).
- Before: Unchanged upstream: cross-runtime discovery and host-reload regressions; `3 failed, 130 deselected in 5.94s`.
- After: `5313 passed, 35 skipped, 9 warnings in 303.99s (0:05:03)` from `make all PYTEST_JOBS=2` with `--dist=loadfile`; Ruff and strict mypy also passed.
- Coverage: 10 new scenarios: two registries; shared/admin/private and null ownership; existing identity; stopped, disabled, deleted, unshared and removed members.

The tests use synthetic fixtures and temporary databases. Native Windows, a real operator upgrade, paid model requests and live platform/provider services were not validated.
