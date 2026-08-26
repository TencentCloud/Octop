# Octop desktop (Wails v3 + green portable)

All desktop-client code lives here. This is **not** `src/octop/infra/desktop`
(remote desktop streaming).

| Path | Role |
|------|------|
| [`portable/`](portable/) | Green zip packaging (was `scripts/green/`) |
| [`src/`](src/) | Wails v3 shell: load bundled zip, spawn Octop, tray/settings |
| [`package-release.sh`](package-release.sh) | Native end-to-end portable + Wails release build |

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

CI: `.github/workflows/octop-portable.yml` builds all six native platform/arch
variants. Each job first creates the green zip and then packages the matching
zip with its Wails application.

## Build a complete desktop release

Run the end-to-end script on the matching native host. It builds the Dashboard,
creates and verifies the portable runtime, embeds it into Wails, and produces
the final archive:

```bash
desktop/package-release.sh
# Reuse an existing desktop/portable/release/Octop-<plat>.zip:
desktop/package-release.sh darwin-arm64 --reuse-portable
```

Wails requires native packaging, so all six variants are produced by the CI
matrix on macOS, Linux, and Windows runners rather than cross-compiled locally.

## Build the Wails shell

Run these from **`desktop/src`** (that directory contains `Taskfile.yml` and
`build/config.yml`). Requires **Go 1.25+**, [Wails v3](https://v3.wails.io/)
`v3.0.0-beta.13`.

```bash
go install github.com/wailsapp/wails/v3/cmd/wails3@v3.0.0-beta.13
cd desktop/src
go mod tidy
wails3 build            # development binary under desktop/src/bin/
wails3 task package ARCH=arm64 \
  PORTABLE_ZIP=../portable/release/Octop-darwin-arm64.zip
```

Dev against an already-running Octop (skips the bundled green zip):

```bash
cd desktop/src
OCTOP_DESKTOP_URL=http://127.0.0.1:8088 wails3 dev
```

Without `OCTOP_DESKTOP_URL`, first launch uses `~/.octop/portable/` if valid,
otherwise extracts the matching zip shipped with the desktop package (embedded
in the Windows `.exe`, under `Contents/Resources` on macOS, beside the binary
on Linux). The Wails shell never downloads Octop. For local runtime debugging, set
`OCTOP_DESKTOP_PORTABLE_ZIP=/absolute/path/Octop-<plat>.zip`.

Desktop outputs are named `Octop-Desktop-<plat>.zip` on macOS/Windows and
`Octop-Desktop-<plat>.tar.gz` on Linux. Runtime upgrades remain owned by Octop:
the shell sets `OCTOP_GREEN_PACKAGES`, so `octop update` upgrades the extracted
`packages/` directory through Octop's existing `--target` logic.

Linux also needs GTK4 + WebKitGTK 6 to link. macOS 12+.
