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
self-updates. CI builds the green zips and bundles each one with the Electron
shell and Dashboard in a matching native installer.

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
when a blocked package needs one. `electron` is not on that list: since
Electron 45 the package has no postinstall, and `node_modules/electron/dist/` is
populated on first use — `pnpm dev` triggers it through `require("electron")`,
CI can do it explicitly with `npx install-electron`.

Node is pinned to **24** by `src/mise.toml`, overriding the repo-root pin of
20. That override is scoped to this directory and nowhere else: the Dashboard,
`docker/Dockerfile` (`node:20-slim`), `release.yml`, `fnos-build-fpk.yml`,
`octop-desktop.yml` and the server all stay on Node 20. The reason for the split
is `pnpm test`, which uses `node --test --experimental-strip-types` and needs
Node ≥22.6 (on Node 20 the runner dies with `bad option`), plus Node 20's April
2026 EOL. This only affects build/test tooling: the shipped app runs on
Electron's bundled Node (Electron **45.0.0** → Node 24.22.0, Chromium 156), so
raising the app's runtime Node means upgrading Electron, not this pin.

```bash
cd desktop/src
mise install                    # node 24 + pnpm 12.15.0
pnpm install --frozen-lockfile
pnpm typecheck && pnpm test && pnpm build
pnpm dev                        # build everything, then launch (repo source)
pnpm dev:start                  # relaunch the existing out/ bundle (no build)
pnpm dev:no-sandbox             # same, minus the Chromium sandbox + GPU process
pnpm package                    # electron-builder (requires staged resources)
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

## Accounts (no sign-in wall)

Desktop builds run without the account system. `buildSidecarEnv()` gives the
sidecar `OCTOP_REQUIRE_SETUP_PASSWORD=0`, so the wizard skips its CLI password
and the first admin gets a server-minted password nobody ever types
(`POST /api/setup/initial-admin` accepts a body without `password`). The JWT
lifetime is left at the server default: the session is renewed, not lengthened.

The Dashboard is not desktop-specific: it reads `wizard_password_required`
from `/api/setup/status` and hides the password step plus the Admin step's
password fields. A web deployment keeps the default `true` and the same code
renders them again. While the shell runs `OCTOP_REQUIRE_SETUP_PASSWORD` is
shell-owned — the `~/.octop/env` file and `PUT /api/envs` cannot put the
sign-in wall back.

An unknown password would be a dead end the moment the JWT expired, so the
shell holds a **device credential** instead:

- `main/session/device-credential.ts` mints a 32-byte secret on first use and
  stores it encrypted with `safeStorage` (Keychain / DPAPI / libsecret) at
  `<OCTOP_HOME>/desktop-device.json`, mode `0600`. Without an OS keychain the
  secret is stored as-is and the shell logs a warning.
- The renderer never sees it. After the first authenticated response,
  `dashboard/src/api/desktopSession.ts` asks the shell to bind the credential to
  the signed-in user (`POST /api/auth/device/register`, which replaces any
  previous token, so a reinstall or second machine takes over).
- On a `401`, `request()` renews once through the shell
  (`POST /api/auth/device/token`) and retries with the new JWT. The exchange is
  JWT-exempt but requires the shell flag, a loopback peer, a matching SHA-256
  digest (constant-time compare) and stays under a per-host failure throttle —
  only the digest is stored server-side (`secrets` row `desktop_device`).
- `POST /api/auth/device/revoke` forgets the credential; the shell exposes it as
  `session.revoke` for a future "reset this device's login" action.

So a desktop install keeps working across restarts and across JWT expiry without
ever asking for a password. Sliding renewal still rotates the token during use.
The one remaining dead end is deliberate: an admin who *deletes* the credential
(or whose user row is removed) reaches the normal login page, and recovering
from there is a server-side operation (`octop user passwd`), not something the
shell can do on its own.

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
Release, then mirrors it to COS. Each job bootstraps portable CPython, packages
the zip, smoke-tests every frozen requirement, and bundles that exact zip plus
the Dashboard into a native Electron installer. For macOS this produces DMG and
ZIP, for Windows NSIS EXE, and for Linux AppImage, deb and rpm. Installer files
are named `Octop-desktop-<plat>-<version>.<ext>`; the portable manifest records
the original Python version and the bundled zip's SHA-256. Optional CI signing
secrets (`CSC_LINK`, `CSC_KEY_PASSWORD`, `WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD`,
`APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`) are required for a
signed/notarized release; without them the installers are unsigned.

A `v*` tag triggers building all six platform/architecture variants and attaches
both portable and desktop assets to the same GitHub Release. For a trial build
without publishing a release, dispatch `octop-desktop.yml` on the feature branch
with `platforms=all` and `attach_release=false`; download the artifacts from
that workflow run. Do not dispatch on an older tag without the Electron source.
