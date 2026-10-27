# Octop desktop (green portable + Electron shell)

All desktop-client code lives here. This is **not** `src/octop/infra/control/desktop`
(remote desktop streaming).

| Path | Role |
|------|------|
| [`src/`](src/) | Electron shell — owns the Python sidecar, not the business logic |
| [`portable/`](portable/) | Green zip packaging |
| [`DESKTOP_ARCHITECTURE.zh.md`](DESKTOP_ARCHITECTURE.zh.md) | Target architecture for the Electron shell |

The Electron shell owns the whole desktop lifecycle: extract the green runtime,
spawn Octop on a random loopback port, own tray/window chrome, refuse
self-updates. CI keeps building the green zips that the shell bundles;
`electron-builder` packaging is not wired into CI yet, so `pnpm package` is
still a local step.

Inside the Electron package everything sits directly under `src/`: `main/`,
`preload/`, `renderer/`, `shared/`.

## Electron shell (pnpm + Node 24)

`desktop/src` is an independent Node package managed by **pnpm 12.15.0**
(the version `corepack use pnpm` resolves under Node 24). The version is declared
in three places that must stay equal:

| Where | Read by |
|-------|---------|
| `src/package.json` → `packageManager` | corepack, and pnpm's own version check |
| `src/package.json` → `devEngines.packageManager` | pnpm 12 / npm native check (`onFail: error`) |
| `mise.toml` → `[tools] pnpm` | `mise install` / `mise exec`, so PATH has the same binary |

Measured behaviour: running an older pnpm in this directory silently re-execs
12.15.0 (`Done in 4ms using pnpm v12.15.0`), while corepack-invoked mismatches
fail with `ERR_PNPM_BAD_PM_VERSION`. Either way `pnpm-lock.yaml` cannot be
rewritten by a different major.

Config is split by pnpm's own rules — since pnpm 11, `.npmrc` is read **only**
for registry/auth, and the `package.json` `"pnpm"` field is ignored:

| File | Holds |
|------|-------|
| `src/pnpm-workspace.yaml` | `nodeLinker: hoisted`, `allowBuilds` (electron, esbuild, app-builder-bin, …) |
| `src/.npmrc` | `registry` only |

`nodeLinker: hoisted` is required because electron-builder and electron-vite
inspect a flat `node_modules` tree. `allowBuilds` is required because pnpm blocks
postinstall by default and pnpm 12 fails the install (`ERR_PNPM_IGNORED_BUILDS`)
when electron's binary download is blocked.

Node is pinned to **24** by `src/mise.toml`, overriding the repo-root pin of
20. That override is scoped to this directory and nowhere else: the Dashboard,
`docker/Dockerfile` (`node:20-slim`), `release.yml`, `fnos-build-fpk.yml`,
`octop-desktop.yml` and the server all stay on Node 20. The reason for the split
is `pnpm test`, which uses `node --test --experimental-strip-types` and needs
Node ≥22.6 (on Node 20 the runner dies with `bad option`), plus Node 20's April
2026 EOL. This only affects build/test tooling: the shipped app runs on
Electron's bundled Node (Electron 33.x → Node 20.18.3), so raising the app's
runtime Node means upgrading Electron, not this pin.

```bash
cd desktop/src
mise install                    # node 24 + pnpm 12.15.0
pnpm install --frozen-lockfile
pnpm typecheck && pnpm test && pnpm build
pnpm dev                        # build everything, then launch (repo source)
pnpm dev:start                  # relaunch the existing out/ bundle (no build)
pnpm dev:no-sandbox             # same, minus the Chromium sandbox + GPU process
pnpm package                    # electron-builder release
```

All three launch scripts are `scripts/run-dev.sh` with different flags; `--`
forwards the rest of the line to the Electron binary:

```bash
pnpm dev:start -- --lang=en-US --remote-debugging-port=9222
```

`Ctrl+C` stops the shell **and** its Python sidecar. Chromium puts the browser
process in its own session, so the terminal's signal does not always reach it,
and Python runs detached (§3.1) — a signal that only kills the wrapper would
strand the backend holding the database. So the wrapper traps the signal,
forwards it to Electron, and Electron stops Python before exiting; a second
`Ctrl+C` skips the 5s grace window.

### Why the launch flags

`run-dev.sh` always drops `ELECTRON_RUN_AS_NODE` for the launch (and only for
the launch). When that variable is set to anything — some shells and CI images
export it globally — the Electron binary runs as a plain `node`, so
`require("electron")` returns a path string instead of the API and the first
line of `main/index.ts` dies with
`Cannot read properties of undefined (reading 'registerSchemesAsPrivileged')`.

`--no-sandbox` is **not** the default, because it removes Chromium's renderer
isolation. Reach for `pnpm dev:no-sandbox` only where the setuid helper cannot
initialise (`sandbox initialization failed: Operation not permitted`) or the GPU
process dies (`GPU process exited unexpectedly`): containers, CI, headless
hosts, locked-down sandboxes. It is a dev-host switch and must never reach a
packaged build.

`dashboard/` is still npm-managed (`dashboard/package-lock.json`); the two
package managers never share a `node_modules` tree.

## Update flow (shell-owned)

`openUpdateConfirmation()` is the only update entry point the renderer has, and
it takes **no arguments** — the Dashboard can ask for the dialog, but it cannot
name a package URL or pre-authorize an install.

1. `main/update/update-coordinator.ts` selects the release from the manifest
   (stable/beta preference, never a downgrade, `https` + `download.octop.cloud`
   only).
2. `main/update/download.ts` streams the installer into `$TMPDIR/octop-update`
   and reports progress to the taskbar/Dock.
3. API admission closes (the `octop://app/api/*` proxy answers `503`), then
   `SidecarSupervisor.stop()` waits for Python to exit **by itself with code 0**.
   A forced kill or non-zero exit cancels the install instead of replacing files
   under a live backend.
4. `main/update/installer.ts` hands the file to the OS installer — `dmg`/`pkg`
   through `shell.openPath`, `exe`/`msi` spawned detached on Windows, AppImage
   `chmod +x` first — and the shell quits so the installer can replace it.
5. If the installer never opens, the sidecar is restarted and the window
   reloads, so a failed hand-off does not leave a dead backend.

Not covered yet: the §3.4 "running tasks" confirmation before quit (the backend
has no task-query endpoint) and manifest-level digests — release assets carry no
checksum, so only the pinned-download-host rule is enforced.

## Data directory

Same as the Octop CLI/server default:

- `OCTOP_HOME` → `~/.octop` (or the existing `OCTOP_HOME` env)
- Green runtime extract → `~/.octop/portable/`
- Shell prefs → `~/.octop/desktop-settings.json`

The shell points `OCTOP_GREEN_PACKAGES` at the extracted `packages/` directory, so
`octop update` upgrades it through Octop's existing `--target` logic. Newer
extracted runtimes are never downgraded; PostgreSQL stays externally managed and
is not copied by the shell.

## Build green zip

From repo root:

```bash
make -f desktop/portable/Makefile green
```

CI: `.github/workflows/octop-desktop.yml` builds native platform/arch variants
(`darwin-arm64`, `darwin-amd64`, `linux-arm64`, `linux-amd64`, `windows-arm64`,
`windows-amd64`) and attaches `Octop-portable-<plat>-<version>.zip` to the GitHub
Release, then mirrors it to COS. Each job builds the Dashboard, bootstraps the
portable CPython, packages the zip, and smoke-tests the bundle by importing every
frozen requirement.
