---
name: octop-browser
description: AI browser automation via CDP. Use when you need to control a browser, navigate pages, click elements, fill forms, extract content, or take screenshots.
allowed-tools: Bash
---

# octop-browser Browser Automation

You drive a real Chrome browser via the Chrome DevTools Protocol (CDP) by
running the `octop-browser` CLI through the Bash tool. Each invocation
attaches to the same Chrome process per profile, so a sequence of commands
shares one persistent session.

## Core Rules

1. **Always run `dom-tree` before `click`** — refs expire on navigation.
2. **Default to `--level interactive`** (~200-500 tokens) to get clickable/typeable elements.
3. **Use `--level minimal`** (~50 tokens) only to confirm page state or URL.
4. **Use `--level full`** (~1000-3000 tokens) only when reading page content.
5. **Use `--level structured`** when you need JSON for programmatic processing.
6. **Never hardcode coordinates** — always pass `--ref` from `dom-tree`.
7. **Use named profiles** to persist login state across runs: `--profile work`, `--profile github`.
8. **On CDP error**: run `dom-tree --level minimal` to check state, then retry.
9. **Tear down with `close-session --profile <name>`** when finished — Chrome itself keeps running so you can reattach later.

## Standard Workflow

```bash
# 1. Navigate
octop-browser navigate "https://example.com" --profile default

# 2. Get interactive elements with refs
octop-browser dom-tree --profile default
# Output:
#   [ref=inp_1] input[text] placeholder="Search"
#   [ref=btn_2] button "Search"

# 3. Act using refs — never coordinates
octop-browser click --ref inp_1 --profile default
octop-browser type "hello" --profile default
octop-browser click --ref btn_2 --profile default

# 4. (optional) capture proof
octop-browser screenshot --path /tmp/result.png --profile default
```

Add `--json` to any command when you want the full structured `ToolResult`
(success / content / metrics / metadata / error) instead of the human-readable
default.

## Commands Reference

| Command | Required args | Common options |
|---|---|---|
| `navigate <url>` | url | `--profile`, `--json` |
| `dom-tree` | — | `--level {minimal,interactive,full,structured}` |
| `screenshot` | — | `--full-page`, `--element-ref REF`, `--path PATH` |
| `click` | one of `--ref REF` / `--selector CSS` / `--xy X Y` | |
| `type <text>` | text | `--ref REF` (click before typing) |
| `scroll` | — | `--direction {up,down,left,right}`, `--amount N` |
| `hover <ref>` | ref | |
| `eval-js <expression>` | expression | |
| `go-back` / `go-forward` / `reload` | — | |
| `list-tabs` | — | |
| `new-tab` | — | `--url URL` |
| `switch-tab <tab_id>` | tab_id | |
| `close-tab` | — | `--tab-id ID` |
| `close-session` | — | (only `--profile`) |

All action commands accept `--profile`, `--json`, and one of
`--auto` / `--headed` / `--headless` (the launch-mode flag is only honoured
on the *first* call per profile — Chrome is reused after that).

## Screenshots

`screenshot` writes a PNG to disk and prints its **path** (not base64).
With `--json`, the response also includes `metadata` carrying
`url` / `title` / `width` / `height` / `size_kb` / `full_page`.

- Default path: `BROWSER_USE_SCREENSHOTS_DIR/octop-<timestamp>.png`
  (default `~/.octop-browser/screenshots/`)
- `--full-page` — capture the entire scrollable page in one call
- `--element-ref btn_2` — crop to a specific element (mutually exclusive
  with `--full-page`; element wins)
- `--path /tmp/latest.png` — pin the file path; every call overwrites it

## Configuration (environment variables)

All knobs are env-driven; no code changes between dev / CI / prod.

| Variable | Default | Use |
|---|---|---|
| `BROWSER_USE_MODE` | `auto` | `auto` / `headed` / `headless` (auto picks based on `DISPLAY`) |
| `BROWSER_USE_PROFILES_DIR` | `~/.octop-browser/profiles` | Where Chrome user-data-dirs live |
| `BROWSER_USE_SCREENSHOTS_DIR` | `~/.octop-browser/screenshots` | Default screenshot output directory |
| `BROWSER_USE_CHROME_BIN` | auto-detect | Path to Chrome (also auto-detects Playwright's bundled Chromium) |
| `BROWSER_USE_CDP_HOST` | `localhost` | Remote/Docker Chrome host |
| `BROWSER_USE_CDP_WS_URL` | — | Bypass launcher; connect directly to a WS URL |

## Login State Reuse

Profile data lives in `~/.octop-browser/profiles/<name>/`. Reusing the same
profile name in future sessions reuses Chrome cookies — no re-authentication
needed.

```bash
# First run: log in manually (needs a desktop / headed mode)
octop-browser navigate "https://github.com/login" --profile github --headed
# ... complete login in browser ...

# All future runs: login reused automatically
octop-browser navigate "https://github.com" --profile github
```

## Installation

```bash
pip install octop-browser

# Chrome or Chromium required:
# Ubuntu: sudo apt install chromium-browser
# macOS:  brew install --cask google-chrome
# Or, no system browser: octop-browser install-browser
#   (auto-installs `playwright` then downloads a Chromium binary; set
#    OCTOP_SKIP_PLAYWRIGHT_PIP=1 to skip the pip step)
```

## Python API (alternative)

If you'd rather embed octop-browser in a Python script instead of shelling
out, the same actions are available as `from octop_browser import browser_tool`
returning a `ToolResult`. The CLI is the recommended path for skill / agent
use — it's stateless from the caller's perspective and round-trips through
the shell cleanly.

## Repository

https://github.com/TencentCloud/octop-browser
