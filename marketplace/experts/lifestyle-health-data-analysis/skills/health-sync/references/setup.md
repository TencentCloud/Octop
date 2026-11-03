# Health Sync Setup Reference (Bot View)

This is the authoritative setup flow for ClawHub bots.

Only one onboarding flow is supported:

1. Bot creates bootstrap token.
2. Bot tells user to run remote onboarding locally.
3. User sends encrypted archive.
4. Bot imports archive locally.

Legacy setup flows are out of scope for bot guidance.

The bot must actively guide the user step-by-step through this flow.
Do not just send one command and stop; confirm each phase before continuing.

## Command Summary

Bot-side commands:

1. `npx health-sync init remote bootstrap --expires-in 24h`
2. `npx health-sync init remote finish <bootstrap-ref> <archive-path>`
3. `npx health-sync providers --verbose`
4. `npx health-sync sync`
5. `npx health-sync status`

User-side command:

1. `npx health-sync init --remote <bootstrap-token>`

## User Prerequisite Guidance (`npx` and npm)

When the user is unsure what `npx` is, or reports `npx: command not found`, the bot must guide them through prerequisites before retrying setup.

Use this sequence:

1. Ask user to check existing tools:

```bash
node -v
npm -v
npx --version
```

2. If npm/npx is missing, tell user to install Node.js LTS (which includes npm and npx):
   - macOS (Homebrew): `brew install node`
   - Ubuntu/Debian: `sudo apt update && sudo apt install -y nodejs npm`
   - Windows: install Node.js LTS from `https://nodejs.org/`

3. Ask user to close/reopen terminal and rerun:

```bash
node -v
npm -v
npx --version
```

4. Continue onboarding with:

```bash
npx health-sync init --remote <bootstrap-token>
```

## Bot Responsibilities

The bot must:

1. Run bootstrap on bot infrastructure.
2. Share only the single remote command with the user.
3. Never ask user for provider secrets in chat.
4. Receive user archive file.
5. Run finish locally and confirm import.
6. Run verification sync and status.

## Detailed Bot Runbook

### Phase 1: Bootstrap locally (bot machine)

Run:

```bash
npx health-sync init remote bootstrap --expires-in 24h
```

Capture from output:

1. bootstrap token (`hsr1...`)
2. session fingerprint
3. expiry timestamp

### Phase 2: Tell user exactly what to run

Send this instruction pattern:

```text
I created a secure one-time setup token for your Health Sync onboarding.

Please run this on your own machine:
npx health-sync init --remote <TOKEN>

This will walk you through provider setup and generate an encrypted archive.
Send that archive file back here when done.
```

Important guidance to include:

1. User should run command in a local terminal with browser access.
2. User should complete provider auth inside the interactive wizard.
3. User should upload the generated `.enc` archive file to the bot.

### Phase 3: Import archive locally (bot machine)

After receiving the archive:

```bash
npx health-sync init remote finish <TOKEN_OR_KEY_ID_OR_SESSION_ID> /path/to/archive.enc
```

Optional target paths:

```bash
npx health-sync init remote finish <REF> /path/to/archive.enc \
  --target-config /path/to/health-sync.toml \
  --target-creds /path/to/.health-sync.creds
```

Expected finish behavior:

1. decrypts archive
2. validates checksums
3. writes config + creds
4. creates backups if files already existed
5. marks bootstrap session as consumed

### Phase 4: Verify ingestion

Run:

```bash
npx health-sync providers --verbose
npx health-sync sync
npx health-sync status
```

Report:

1. providers discovered/enabled
2. sync success or provider-specific failures
3. current data freshness

## What The Bot Should Never Do

Do not ask users to:

1. paste `client_secret`, `api_key`, OAuth callback URLs, access tokens, or passwords into chat
2. run `health-sync auth <provider>` as onboarding
3. do manual same-machine setup (`health-sync init`) as the primary flow
4. globally install `health-sync` as a first step when `npx health-sync ...` is sufficient

Do not instruct mixed flows. Remote bootstrap is the only setup workflow for ClawHub bot guidance.

## User Experience Copy (Recommended)

### Bootstrap response

```text
Secure setup is ready.
Run this command on your own machine:

npx health-sync init --remote <TOKEN>

The wizard will guide you provider-by-provider and then output an encrypted archive.
Please upload that archive file here when complete.
```

### Archive received response

```text
Archive received. I am now importing your encrypted setup on my side.
```

### Import success response

```text
Setup import complete. I will now run a sync and verify your provider status.
```

## Failure Handling

1. Token expired:
   - Generate a new bootstrap token.
2. Session already consumed:
   - Start a fresh bootstrap and rerun user command.
3. Archive does not match token/session:
   - Confirm user used the latest token.
4. User reports no archive generated:
   - Ask them to rerun `npx health-sync init --remote <TOKEN>` and complete provider auth steps.
5. User reports `npx` not found:
   - Guide npm installation using the prerequisite section above, then retry.

## Security Notes

1. Treat bootstrap tokens as sensitive and short-lived.
2. Keep bot bootstrap storage private.
3. Treat imported `health-sync.toml` and `.health-sync.creds` as secrets.
4. Do not commit secret files to version control.

## Architecture Notes

This setup reference is intentionally self-contained for skill runtime.

If a runtime platform cannot resolve repository-level docs paths, continue using this file as the authoritative bot runbook for remote bootstrap onboarding.
