# Windows Desktop Packaging

Octop's Windows desktop package is built on Windows, not macOS:

```text
macOS development machine
  -> push code to GitHub
  -> GitHub Actions windows-latest
  -> PyInstaller onedir
  -> Inno Setup
  -> Octop-Setup-x.y.z.exe
```

## Build outputs

The packaging workflow produces:

```text
dist/Octop/                  # PyInstaller onedir app
dist/installer/Octop-Setup-x.y.z.exe
```

The installed program lives under the selected installation directory, typically:

```text
C:\Program Files\Octop\
```

User data remains separate:

```text
C:\Users\<name>\.octop\
```

Upgrades and reinstalls should not overwrite agents, skills, plugins, chat history, or `config.json`.

## Desktop entry

The packaged executable runs:

```text
octop.desktop_app:main
```

At runtime it:

1. starts `OctopServer`;
2. builds the existing FastAPI app with `build_app(server)`;
3. binds the backend to `127.0.0.1` on a random port by default;
4. opens the current React dashboard in a PyWebView window;
5. stops the backend when the desktop window exits.

Desktop mode sets `OCTOP_REQUIRE_SETUP_PASSWORD=0` by default because the app is
loopback-only and the packaged Windows executable has no visible terminal. This
keeps first-run setup inside the desktop window instead of asking a non-technical
user to find a generated `octop-login.txt` password file. Normal `octop run`
behavior is unchanged.

For installer smoke tests, the same executable supports a backend-only mode:

```powershell
Octop.exe --no-window --port 18088
```

## Playwright

Playwright remains a core capability. The Windows workflow sets:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
uv run python -m playwright install chromium
```

This installs Chromium into the Python environment so PyInstaller can collect it with the Playwright package data. Browser bundle failures should be fixed in the PyInstaller spec rather than by removing Playwright from the desktop build.

## Manual release flow

1. Push the branch or tag to GitHub.
2. Run the `Windows Desktop Installer` workflow manually, or push a `v*` tag.
3. Download the `octop-windows-installer` artifact.
4. Copy `Octop-Setup-x.y.z.exe` to a Windows machine.
5. Install it normally and launch Octop from the Start Menu or desktop shortcut.

## First Windows checks

On a test Windows machine:

1. Install `Octop-Setup-x.y.z.exe`.
2. Launch Octop.
3. Confirm the desktop window opens rather than a browser tab.
4. Complete existing setup/login in the dashboard.
5. Close the window.
6. Confirm no `Octop.exe` process is left running.
7. Reinstall or upgrade and confirm `C:\Users\<name>\.octop\` data is still present.
