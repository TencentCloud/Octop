# Octop desktop (Wails v3 + green portable)

All desktop-client code lives here. This is **not** `src/octop/infra/desktop`
(remote desktop streaming).

| Path | Role |
|------|------|
| [`portable/`](portable/) | Green zip packaging (was `scripts/green/`) |
| [`src/`](src/) | Wails v3 shell: download zip, spawn Octop, tray/settings |

## Data directory

Same as the Octop CLI/server default:

- `OCTOP_HOME` → `~/.octop` (or the existing `OCTOP_HOME` env)
- Green runtime extract → `~/.octop/portable/`
- Shell prefs → `~/.octop/desktop-settings.json`

## Build green zip

From repo root:

```bash
make -f desktop/portable/Makefile green
```

CI: `.github/workflows/octop-portable.yml` (unchanged location).

## Build the Wails shell

Requires **Go 1.25+** and [Wails v3](https://v3.wails.io/) (`wails3`).

```bash
cd desktop/src
go mod tidy
# generate bindings if you have the CLI:
#   wails3 generate
wails3 build
```

Dev against an already-running Octop:

```bash
OCTOP_DESKTOP_URL=http://127.0.0.1:8088 wails3 dev
```

First launch without that env downloads `Octop-<plat>.zip` from the latest
GitHub Release (`OCTOP_DESKTOP_GITHUB_REPO`, default `forcemeter/Octop-Agent`).
