# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Commands

All targets run through `uv` and the Makefile:

```bash
make all       # ship bar: format + lint + typecheck + test — what pre-commit runs
make format    # ruff check --fix + ruff format on src/ tests/ (rewrites files)
make lint      # ruff check + ruff format --check on src/ tests/
make typecheck # mypy strict on src/
make test      # full suite with coverage (uv run pytest --cov=octop_browser)
make build     # uv build → wheel + sdist
make mcp       # launch the MCP stdio server (python -m octop_browser.mcp_server)
make publish   # local uv publish (prefer /publish skill + Actions; do not use for public releases)
make clean     # remove dist/, .coverage, .mypy_cache/, .ruff_cache/
```

**Git hooks (required before committing):** run **`make install-hooks`** once per clone. It sets `core.hooksPath=.githooks`, so every `git commit` first runs **`make all`** (`format` rewrites files, then lint / typecheck / test). Staged files rewritten by `format` are re-added automatically, so the commit contains the formatted content. This replaces the `pre-commit install` route — `core.hooksPath` overrides `.git/hooks/`, and `make all` is a superset of `.pre-commit-config.yaml` (ruff + ruff-format + mypy, plus tests). Bypass only in emergencies: `SKIP_PRECOMMIT=1 git commit …` or `git commit --no-verify`; never skip hooks to land a red suite.

Useful narrower invocations:

```bash
# Unit tests only — no Chrome required
uv run pytest tests/unit/ -q

# A single test file or test
uv run pytest tests/unit/test_mode.py -q
uv run pytest tests/unit/test_settings.py::test_env_override_browser_mode -q

# Integration tests — auto-skipped when Chrome/Chromium is not on the host
uv run pytest tests/integration/ -v

# Type-check or lint just one path
uv run mypy src/octop_browser/session.py
uv run ruff check src/octop_browser/cdp/

# Install dev extras + enable the commit gate
uv sync --extra dev
make install-hooks
```

`pytest-asyncio` runs in `asyncio_mode = "auto"` (set in `pyproject.toml`) — async test functions need no decorator. `tests/integration/conftest.py` skips the whole integration suite when `find_chrome()` returns None, so unit work on machines without Chrome stays green.

## Architecture

This package wraps Chrome over **pure CDP** (WebSocket, no Playwright) and exposes it three ways: an async Python API, a stateless `browser_tool()` for AI frameworks, and an MCP server. Understanding the call chain matters when changing anything in the launch / connect / DOM path.

### Layered call chain

```
browser_tool()  ──► BrowserSession ──► _InternalCDPSession ──► CDPClient (websockets) ──► Chrome
mcp_server.py   ──┘                          │
                                             └─► launcher.launch_or_attach + get_page_ws_url
```

- `tool_interface.browser_tool(action, profile=..., mode=...)` — stateless dispatch keyed by `profile`. Maintains a `_registry: dict[str, BrowserSession]`; first call per profile creates a session, subsequent calls reuse it. Action names map directly to `BrowserSession` methods via `getattr`.
- `session.BrowserSession` — public async API. Mixes in `HooksMixin` (events: `before_action`, `after_action`, `action_error`; `page_navigated` is reserved and never fired) and accumulates running totals in `metrics_summary()`.
- `session._InternalCDPSession` — owns one `CDPClient` + one `RefCache` per page. Honors `cfg.cdp_ws_url`: if set, **bypasses the launcher entirely** and connects directly to the given WebSocket (used for remote/Docker Chrome).
- `cdp.client.CDPClient` — minimal CDP framing over `websockets.asyncio.client`. `send(method, params)` returns the result; `enable_domain()` enables `Page` / `DOM` / `Runtime` / `Input` after connect.
- `cdp.launcher` — `find_chrome()`, `launch_or_attach()` (re-attach if port is already serving CDP), `_get_ws_url()` polls `http://{cdp_host}:{port}/json/version`, `get_page_ws_url()` picks the first `type==page` target. All HTTP probes go through `aiohttp` and **always read `cdp_host` from settings** — never hardcode `localhost`.

### Configuration: OctopSettings (single source of truth)

`settings.OctopSettings` is a `dataclass` whose every field uses `field(default_factory=lambda: _env_*(...))`. This means **each instantiation re-reads env vars**, which is what `monkeypatch.setenv` in tests relies on. The module-level `settings` singleton (read at import time) is the default everywhere; tests should construct a fresh `OctopSettings()` rather than mutating it.

Env vars (all optional):

| Variable | Default | Used in |
|---|---|---|
| `BROWSER_USE_PROFILES_DIR` | `~/.octop-browser/profiles` | `ProfileManager.__init__` |
| `BROWSER_USE_CDP_HOST` | `localhost` | `launcher._get_ws_url`, `_port_in_use`, `get_page_ws_url`, `session.list_tabs`; also drives `--remote-debugging-address` when non-loopback |
| `BROWSER_USE_CDP_PORT_START` | `9222` | `ProfileManager` port assignment |
| `BROWSER_USE_MODE` | `auto` | resolved via `mode.resolve_headless()` |
| `BROWSER_USE_CHROME_BIN` | auto-detect | `launcher.find_chrome` (checked before path search) |
| `BROWSER_USE_CDP_TIMEOUT` | `30.0` | `CDPClient` send timeout |
| `BROWSER_USE_LAUNCH_RETRIES` / `BROWSER_USE_LAUNCH_DELAY` | `20` / `0.25` | launcher polling |
| `BROWSER_USE_CDP_WS_URL` | — | `_InternalCDPSession.connect` direct-connect path |
| `BROWSER_USE_IDLE_TIMEOUT_MINUTES` | `0` | local profile idle reaper; real CDP commands refresh the deadline |

The MCP server has no per-tool `inputSchema` field for these — they are passed via the standard `mcpServers.<name>.env` block in client config. Do not add them to the tool schema.

### Browser mode resolution (octop_browser/mode.py)

Three modes — `auto` / `headed` / `headless`. Resolution priority in `BrowserSession.create()`:

1. Explicit `headless=True/False` argument (legacy escape hatch, wins outright)
2. Explicit `mode=` argument
3. `cfg.browser_mode` (from `OctopSettings`, which reads `BROWSER_USE_MODE`)

`auto` calls `has_desktop_environment()`: True on macOS/Windows always; on Linux requires `$DISPLAY` or `$WAYLAND_DISPLAY`. The result is fed to `resolve_headless()`. `_build_flags` only appends `--headless=new` when the resolved bool is True.

### DOM output: 4 levels and the ref system

- `dom.builder.DOMBuilder` produces `minimal` (~50 tok) / `interactive` (~200–500 tok) / `full` (~1000–3000 tok) / `structured` (JSON) views from a CDP `DOM.getDocument` snapshot.
- `dom.refs.RefCache` issues stable refs like `btn_2`, `inp_search` mapping `ref → CDP nodeId`. **Refs are invalidated on navigation** — `nav_actions.navigate` / `go_back` / `go_forward` / `reload` clear the cache. Any new navigation-class action MUST do the same or you'll hand the agent stale node IDs.
- Token estimate is `len(content) // 4` — keep this when adding new actions that build text content.

### Profiles and login persistence

`profile.ProfileManager` allocates one `Chrome --user-data-dir` per profile name under `cfg.profiles_dir`, with `cdp_port = cfg.cdp_port_start + index`. This is the entire login-persistence story: same profile name → same data dir → cookies and storage reused. Don't add ad-hoc paths for cookies/auth — go through `Profile`.

### Hooks and metrics

`HooksMixin` is what `BrowserSession` mixes in. Every action goes:

```
_fire("before_action", {...}) → action body → _record(result)
                                                  └─► _fire("after_action", metrics)  (or "action_error")
```

`ActionMetrics` (`models.py`) carries `duration_ms`, `dom_nodes_scanned`, `estimated_tokens`, `screenshot_size_kb`. `BrowserSession.metrics_summary()` aggregates totals across the session.

### Skill files (Claude Code / agent-facing)

Live at `skills/octop-browser/SKILL.md` (English) and `skills/octop-browser-zh/SKILL.md` (Chinese). They use the standard YAML-frontmatter format (`name`, `description`, `allowed-tools`) and are designed to be `cp -r`'d into other agent projects. Keep these in sync when the public surface (env vars, modes, action list) changes.

## Project conventions

- **Commit gate**: `make install-hooks` once per clone; `make all` must be green before every commit (the hook enforces it). See [Commands](#commands).
- **Docs language**: README is bilingual (`README.md` canonical English + `README_CN.md`); `CHANGELOG.md` and `CONTRIBUTING.md` are Chinese-only by deliberate choice.
- **ruff**: `line-length = 88`, lint selects `E F I N W`. Do not raise the line length to dodge wraps.
- **mypy**: `strict = true`, `python_version = "3.11"`. New code must type-check under strict mode; reach for `from __future__ import annotations` (already used everywhere) before adding `# type: ignore`.
- **No Playwright, no Selenium**: the dependency story is just `websockets`, `aiohttp`, `pydantic`, `mcp`. Don't add browser drivers.
- **`localhost` is never hardcoded** — always go through `cfg.cdp_host`. A dedicated regression hazard if you forget.
- **Repository URL** in docs is `https://github.com/TencentCloud/octop-browser.git`.

## Branching & release

Follow Octop-style flow documented in `CONTRIBUTING.md`:

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
```

Agent publish: `.cursor/skills/publish` (`/publish <version>`). Never push directly to `main`/`develop`.

