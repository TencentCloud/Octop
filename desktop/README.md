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

Run these from **`desktop/src`** (that directory contains `Taskfile.yml` and
`build/config.yml`). Requires **Go 1.25+**, [Wails v3](https://v3.wails.io/)
`v3.0.0-beta.13`, and [Task](https://taskfile.dev/) (`task` on `PATH`).

```bash
go install github.com/wailsapp/wails/v3/cmd/wails3@v3.0.0-beta.13
cd desktop/src
go mod tidy
wails3 generate icons   # once: appicon.png → .icns / .ico
wails3 build            # native binary under desktop/src/bin/
```

Dev against an already-running Octop (skips downloading the green zip):

```bash
cd desktop/src
OCTOP_DESKTOP_URL=http://127.0.0.1:8088 wails3 dev
```

Without `OCTOP_DESKTOP_URL`, first launch uses `~/.octop/portable/` if present,
otherwise downloads `Octop-<plat>.zip` from the latest GitHub Release
(`OCTOP_DESKTOP_GITHUB_REPO`, default `forcemeter/Octop-Agent`).

Linux also needs GTK4 + WebKitGTK 6 to link. macOS 12+.
