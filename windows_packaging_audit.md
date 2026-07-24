# Octop Windows Desktop Packaging Audit

## Conclusion

Octop can be turned into a Windows desktop product without rewriting the React UI or FastAPI core, but the current repository cannot yet be reliably frozen into a standalone EXE. Its Windows support is sufficient for a Python/CLI installation and automated tests, not yet for a novice-friendly desktop installer.

The smallest practical design is an embedded Edge WebView2 window that launches the FastAPI backend locally and invisibly. Package the backend as a PyInstaller `onedir` distribution, then wrap that directory in an Inno Setup `Setup.exe`. This gives users a normal Start Menu application and no browser tab or server deployment.

Do not optimize for a literal single-file portable EXE initially. Playwright, native Python wheels, static assets, dynamic plugins, and antivirus false positives make a one-file bundle less reliable. A single installer EXE containing a normal application directory provides the same user experience with fewer failures.

## Route comparison

- **PyWebView + PyInstaller + Inno Setup (recommended):** smallest change for this Python-first codebase; reuses the current React UI inside Edge WebView2. The tradeoff is that desktop window polish and updater integration require some custom Python code.
- **Tauri + frozen Python sidecar:** better native window, tray, signing, and updater ecosystem, but adds Rust/Tauri plus sidecar lifecycle complexity. Prefer this if Windows and macOS will both become first-class desktop products.
- **Native UI rewrite:** removes the embedded-web technology entirely, but duplicates the dashboard and creates the largest maintenance burden. It is not justified for the stated goal.

## What already works on Windows

- A Windows/Python 3.12 CI job installs and tests the project.
- Mutable data is stored through `Path.home() / '.octop'`, and most filesystem work uses `pathlib`.
- The default agent workspace root has an explicit Windows adjustment.
- Browser automation and native desktop capture/input contain Windows paths or platform branches.

These are good foundations, but CI does not build or smoke-test a frozen application.

## Blocking gaps

### Product lifecycle

- No desktop host or Windows packaging configuration exists.
- The Windows script installs Python, uv, a virtual environment, and packages from the network.
- Background service management only supports systemd and launchd, although the Windows installer suggests `octop service start`.
- Self-update modifies the Python environment with pip/uv; a frozen application needs installer-based updates instead.

### Shell behavior

- Agent command execution ultimately uses `subprocess.run(..., shell=True)`. On Windows that selects `cmd.exe`, while many model-generated and bundled-skill commands assume POSIX tools and Bash syntax.
- SkillHub auto-install explicitly requires `curl` plus `bash`.
- The dashboard terminal is deliberately disabled on Windows because it requires a POSIX PTY.

Internal subprocess calls that pass argument arrays with `shell=False` are generally not the main problem. The higher-risk area is the free-form command tool and skill content.

### Frozen Python behavior

- Lazy CLI imports need freezer hidden imports or a dedicated desktop entry point.
- Static dashboard, JSON translations, SQL migrations, templates, skills, images, and other package data require an explicit freezer manifest.
- Playwright's Chromium cannot be assumed to appear inside the bundle automatically.
- Bot-creator helpers launch Python source files through `sys.executable`; this breaks when `sys.executable` is the frozen app.
- Plugins may install dependencies with pip at runtime, which a sealed executable cannot safely support.

## Recommended implementation sequence

1. Add a Windows desktop entry point that starts FastAPI on `127.0.0.1` using an available random port, creates a per-launch token, opens an embedded WebView2 window, and stops the backend when the window exits.
2. Create a PyInstaller `onedir` build with explicit hidden imports and data assets. Make browser automation optional on first install.
3. Build an Inno Setup installer with shortcuts, uninstall support, logs, and optional Start-with-Windows registration. Do not use the existing system-service command on Windows.
4. Add a Windows execution adapter using PowerShell semantics and platform-aware command guidance. Audit the default/bundled skills; mark Linux-only skills unavailable on Windows.
5. Adapt frozen subprocess flows into app subcommands/helper executables, and replace pip-based self-update with signed installer download and restart.
6. Add CI that builds the installer on `windows-latest`, installs it silently in a clean VM, launches it, checks `/api/health`, opens the embedded UI, and performs one basic agent flow with a mocked LLM.

## Suggested scope for the first release

Ship chat, agents, providers, files, memory, cron, and the embedded dashboard first. Defer or explicitly disable the POSIX terminal, Linux virtual desktop setup, automatic SkillHub CLI installation, dependency-bearing plugins, and complex bot-creator subprocesses until their Windows/frozen paths are implemented.

This keeps the change surgical: the application core stays intact, and the work is concentrated in the desktop launcher, packaging manifest, lifecycle handling, and platform adapters.
