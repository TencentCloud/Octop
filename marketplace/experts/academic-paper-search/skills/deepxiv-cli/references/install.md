# Installing deepxiv

`deepxiv` is a Python package distributed as `deepxiv-sdk`. It requires **Python 3.10+**. The recommended installer is `pipx` (isolated, cross-platform), but how you obtain `pipx` and which interpreter name to use depends on the OS.

> **Always ask the user before running install commands.** Skills should not modify the user's environment or install system packages without explicit consent. Detect the platform first (`uname -s` on Unix, PowerShell on Windows) and present the matching block for the user to approve.

## macOS

```bash
brew install pipx
pipx install deepxiv-sdk
```

No Homebrew? Use the generic Python bootstrap below.

## Linux — Debian / Ubuntu

```bash
sudo apt update && sudo apt install -y pipx
pipx install deepxiv-sdk
```

## Linux — Fedora / RHEL

```bash
sudo dnf install -y pipx
pipx install deepxiv-sdk
```

## Linux — Arch

```bash
sudo pacman -S python-pipx
pipx install deepxiv-sdk
```

## Generic (any OS without a system pipx)

Use the platform's Python interpreter — `python3` on macOS/Linux, `python` on Windows:

```bash
# macOS / Linux
python3 -m pip install --user pipx
pipx install deepxiv-sdk
```

```powershell
# Windows PowerShell
python -m pip install --user pipx
pipx install deepxiv-sdk
```

If `pipx` is not on PATH after installing, the user may need to restart their shell or run `pipx ensurepath` themselves.

## Last-resort fallback: pip --user

Less isolated than pipx; use only when pipx is unavailable:

```bash
# macOS / Linux
python3 -m pip install --user deepxiv-sdk
```

```powershell
# Windows
python -m pip install --user deepxiv-sdk
```

## Python version pitfalls

- Python 3.9 may install the package but crash on first call. Verify with `python3 --version` (macOS/Linux) or `python --version` (Windows) before installing.
- If the user has multiple Python versions, pin pipx to a modern one: `pipx install --python python3.12 deepxiv-sdk`.

## Verifying

```bash
deepxiv --help
deepxiv health
```

If `deepxiv` is missing after install, the install location is probably not on PATH yet — ask the user to restart their shell.
