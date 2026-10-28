# Local verification: Use the inbound session lock for proactive turns

The screenshot renders actual saved local pytest summaries. It is automated test evidence, not a product UI demonstration or a human-review attestation. Contributor review and hosted CI remain separate.

- Base: `44c22434b090cb78d3a4a2d6fad786e7bbc95863`.
- Tested source blob: `76f5892e4de57cff5f5570769d040f117b6373f9` (`src/octop/infra/gateway/gateway.py`).
- Before: Unchanged upstream: initial six lock-policy/order/cancellation cases; `4 failed, 2 passed in 1.54s`.
- After: `5311 passed, 34 skipped, 9 warnings in 294.99s (0:04:54)` from `make all PYTEST_JOBS=2` with `--dist=loadfile`; Ruff and strict mypy also passed.
- Coverage: 7 final scenarios: real queue and temporary SQLite; text and Agent cron; Feishu/dashboard/CLI; independent subjects; cancellation.

The tests use synthetic fixtures and temporary databases. Native Windows, a real operator upgrade, paid model requests and live platform/provider services were not validated.
