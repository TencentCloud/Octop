Patched Octop - install over your existing Octop (Windows)
==========================================================

This replaces the Octop program in your existing install (%USERPROFILE%\.octop\venv).
Your experts, chats, providers, settings and database stay where they are.
A backup of .octop is made first, to %USERPROFILE%\.octop-backup-<date-time>.

What changed in this build
- Models -> Anthropic: "Test" now calls the real Anthropic API
  (https://api.anthropic.com/v1/messages); before it called /v1/v1/messages and failed.
- Models -> Anthropic: "Fetch models" now uses Anthropic's own /v1/models API
  (x-api-key header) instead of the OpenAI-style one.

Install
  1. Close Octop if it is running.
  2. Unzip this folder.
  3. Open PowerShell in the folder (Shift + right-click -> "Open PowerShell window here") and run:
       powershell -ExecutionPolicy Bypass -File .\install-patched.ps1
  4. Answer the prompts. It asks before stopping Octop or downloading anything new.

Afterwards
  - Start Octop:  octop run   and open http://127.0.0.1:8088
  - Re-test the Anthropic provider under Admin -> Models.

If something goes wrong
  - Close Octop, then copy the files from %USERPROFILE%\.octop-backup-<date-time>
    back into %USERPROFILE%\.octop (leave the venv folder alone).
  - The script prints the command to reinstall your previous Octop version.

Only for the command-line install (the one from install.ps1 / install.bat).
If you use the Octop desktop app, don't run this.

Needs internet: new or updated Python dependencies are downloaded from PyPI.
