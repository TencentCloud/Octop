# Octop Electron green-package integration

This document is the contract for embedding Octop's **green portable zip**
in an Electron (or other) desktop shell. Do not invent a parallel install
path (no system Python, no `PYTHONPATH=packages`).

## Artifact

CI / `make -f desktop/portable/Makefile green` produces:

```
desktop/portable/release/Octop-portable-<plat>-<version>.zip
```

Platforms: `darwin-arm64` `darwin-amd64` `linux-amd64` `linux-arm64`
`windows-amd64` `windows-arm64`.

Layout after extract (outside asar):

```
Octop-<plat>/
  runtime/     portable CPython
  packages/    site-packages
  launch.py
  start.sh / start.bat
```

## Spawn

1. Ship the matching zip with the desktop application. The Wails packages embed
   it in the Windows `.exe`, place it under `Contents/Resources` (macOS), or
   beside the executable (Linux); the desktop shell does not download it at runtime.
2. Extract to a writable user directory **outside** `app.asar`.
3. On macOS, after checksum: `xattr -dr com.apple.quarantine <extractDir>`.
4. Set `OCTOP_HOME` to Octop's default data dir (`~/.octop`, or `$OCTOP_HOME`
   if already set). Do **not** use the zip's `./data` folder when launching
   from the Wails desktop shell (`desktop/src`).
   Extract the zip under `~/.octop/portable/` so runtime files stay next to
   user data without overwriting `octop.db`.
5. Set `PYTHONNOUSERSITE=1` and `OCTOP_GREEN_PACKAGES=<extract>/packages`.
   **Do not set `PYTHONPATH`.**

6. Spawn `launch.py run` **without** `--host` or `--port`. Those flags are
   written back to `config.json`, so a hardcoded `127.0.0.1` undoes the user's
   `bind_host` on every start. Pass them only when the user asked to change
   the saved listen address. If `GET /api/health` on the preferred port is
   already Octop (`ok`, `users_loaded`, and `agents_running`), do not spawn;
   load that URL. Also check `OCTOP_HOME/desktop-port` when the preferred port
   is not Octop: that file is the port a previous desktop start actually bound
   after a conflict, and a live health check there means attach instead of
   starting a second server. If the port is taken by something else, set
   `OCTOP_PORT` to the next free port, then write that port to `desktop-port`.
   The override applies to this process only and is not saved to `config.json`.
   Delete `desktop-port` when the process you started exits. A listen failure
   other than "address already in use" is reported immediately — do not scan
   further ports.

   - macOS / Linux: `<extract>/runtime/bin/python3 <extract>/launch.py run`
   - Windows: `<extract>/runtime/python.exe <extract>/launch.py run`

7. Read `bind_host` and `port` from `OCTOP_HOME/config.json` (defaults
   `127.0.0.1` and `8088` when the file or keys are absent; `OCTOP_BIND_HOST`
   / `OCTOP_PORT` override the file for this process and are not saved).
   When `bind_host` is `0.0.0.0` or `::`, poll and load
   `http://127.0.0.1:<port>/`. Otherwise use the configured host.
8. First run uses the **normal Octop setup wizard** (create admin). The
   green zip does not skip setup or mint loopback sessions.
9. On quit, kill the process **tree** (Windows: taskkill `/T`; POSIX: process group).

## Windows / pywintypes

`No module named pywintypes` means:

1. The process did not start via `launch.py` (plain `PYTHONPATH=packages`
   skips `.pth` processing).
2. `packages\pywin32_system32\pywintypes*.dll` is missing; a current
   package copies those DLLs into `runtime\`.
3. Workaround for an old zip only: `pip install --target packages pywin32`
   then copy DLLs next to `python.exe`. Do not use `%CD%` in PowerShell.

## Health

`GET /api/health` is the ready signal. Do not scrape stdout for “ready”.

## What not to do

- Do not bundle the zip inside asar (native libs and the interpreter must
  be real files).
- Do not use the system Python or `uv run`.
- Do not enable desktop OOB / auto-login overlays; this package tracks
  upstream auth and setup.
