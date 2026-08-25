# Octop Electron green-package integration

This document is the contract for embedding Octop's **green portable zip**
in an Electron (or other) desktop shell. Do not invent a parallel install
path (no system Python, no `PYTHONPATH=packages`).

## Artifact

CI / `make -f scripts/green/Makefile green` produces:

```
green/release/Octop-<plat>.zip
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

1. Download the zip for the current OS/arch. Verify checksum if you ship one.
2. Extract to a writable user directory **outside** `app.asar`.
3. On macOS, after checksum: `xattr -dr com.apple.quarantine <extractDir>`.
4. Set `OCTOP_HOME` to a persistent data dir (not inside the zip if you
   replace the zip on upgrade).
5. Set `PYTHONNOUSERSITE=1`. **Do not set `PYTHONPATH`.**
6. Spawn:

   - macOS / Linux: `<extract>/runtime/bin/python3 <extract>/launch.py run --host 127.0.0.1 --port <port>`
   - Windows: `<extract>/runtime/python.exe <extract>/launch.py run --host 127.0.0.1 --port <port>`

7. Poll `http://127.0.0.1:<port>/api/health` until ready, then load the
   Dashboard (`http://127.0.0.1:<port>/`).
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
