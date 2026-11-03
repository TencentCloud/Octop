# Garmin Connect — OpenClaw Skill

An [OpenClaw](https://openclaw.ai) skill that syncs your daily health data from Garmin Connect into markdown files. OpenClaw can then reference your health and fitness data in conversation.

## What it syncs

- **Sleep** — duration, stages (deep/light/REM/awake), sleep score
- **Body** — steps, calories, distance, floors
- **Heart** — resting HR, max HR, HRV
- **Body Battery & SpO2**
- **Stress** — average level
- **Training Readiness** — score and level
- **Respiration** — waking and sleeping breathing rate
- **Fitness Age**
- **Intensity Minutes** — weekly moderate/vigorous totals
- **Weight** — if recorded
- **Activities** — name, duration, distance, calories, HR, elevation, pace, cadence, power, training effect, VO2 max

## Example output

```markdown
# Health — January 26, 2026

## Sleep: 8h 39m (Good)
Deep: 1h 50m | Light: 4h 30m | REM: 2h 19m | Awake: 0h 54m
Sleep Score: 85

## Body: 9,720 steps | 2,317 cal
Distance: 8.0 km | Floors: 42
Resting HR: 37 bpm | Max HR: 111 bpm
HRV: 68 ms
SpO2: 94.0%

## Training Readiness: 100 (Prime) — Ready To Go

## Respiration: Waking: 12 brpm | Sleeping: 13 brpm | Range: 5–20

## Fitness Age: 33 (6 years younger)

## Intensity Minutes: 385 weekly
Moderate: 69 | Vigorous: 158 | Goal: 150

## Activities
- **5K Run** — 28:15, 5.0 km, 320 cal
  Avg HR 155 / Max 172 | Elevation: +45m | Pace: 5:39/km | Cadence: 168 spm | Training Effect: 3.2 aerobic | VO2 Max: 50
```

Sections are only included when data is available.

## Setup

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (no pip install needed — dependencies are inline)
  - macOS: `brew install uv`
  - Linux/WSL: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- A Garmin Connect account (two-factor authentication must be disabled — see [Troubleshooting](#troubleshooting))

### One-time setup

Authenticate and cache OAuth tokens. This only needs to happen once (~1 year token validity). The password is prompted interactively via `getpass` — never echoed to screen or stored in shell history.

```bash
uv run scripts/sync_garmin.py --setup --email you@example.com
```

After setup succeeds, the password is no longer needed. All subsequent syncs use cached tokens only.

### Run it

```bash
# Sync today (no credentials needed — uses cached tokens)
uv run scripts/sync_garmin.py

# Sync a specific date
uv run scripts/sync_garmin.py --date 2025-01-26

# Sync the last 7 days
uv run scripts/sync_garmin.py --days 7

# Custom output directory (default: health/)
uv run scripts/sync_garmin.py --output-dir my-data
```

Markdown files are written to `health/YYYY-MM-DD.md` by default (relative to the skill's base directory).

### Install as an OpenClaw skill

```bash
ln -s /path/to/garminskill ~/.openclaw/skills/garmin-connect
```

### Cron

Schedule the sync to run every morning so your data stays up to date automatically. No credentials needed — the sync uses cached tokens from the one-time setup. OpenClaw's `cron` tool can handle this, or use a system crontab:

```bash
0 7 * * * uv run /path/to/garminskill/scripts/sync_garmin.py
```

## Troubleshooting

### "No profile from connectapi"

This is the most common setup error. It usually means Garmin's servers are temporarily rate-limiting or blocking the request (via Cloudflare). It does **not** necessarily mean your password is wrong.

1. **Wait a few minutes and try again.** This resolves it most of the time.
2. **Double-check your password.** The error can also appear for wrong credentials — Garmin doesn't always return a clear "wrong password" message.
3. **Check if Garmin Connect is down.** Try logging in at [connect.garmin.com](https://connect.garmin.com) in a browser.

### Two-factor authentication (2FA)

If your Garmin account has 2FA enabled, authentication will fail. The `garminconnect` library does not support 2FA/MFA flows. You'll need to disable 2FA on your Garmin account to use this skill:

1. Log in to [connect.garmin.com](https://connect.garmin.com)
2. Go to Account Settings → Security
3. Disable two-step verification
4. Re-run setup: `uv run scripts/sync_garmin.py --setup --email you@example.com`

### Cloudflare / random auth failures

This skill uses [cloudscraper](https://github.com/VeNoMouS/cloudscraper) to bypass Cloudflare protection on Garmin's SSO. Garmin periodically updates their anti-bot measures, which can cause temporary breakdowns. If authentication suddenly stops working after a period of stability:

1. **Update dependencies:** `uv cache clean` then re-run the sync (uv will fetch the latest versions automatically)
2. **Wait and retry.** Cloudflare blocks are often transient.
3. **Check the [garminconnect issues page](https://github.com/cyberjunky/python-garminconnect/issues)** — others may be experiencing the same problem.

### Tokens expired

Cached tokens last about a year. When they expire, the sync will tell you to re-run setup. Just run the setup command again with your email — a new password prompt will appear and fresh tokens will be cached.

## Auth notes

The script uses [garminconnect](https://github.com/cyberjunky/python-garminconnect) with [cloudscraper](https://github.com/VeNoMouS/cloudscraper) to bypass Cloudflare protection on Garmin's SSO. Authentication is split into two phases:

1. **Setup** (`--setup`): Run once in a terminal to authenticate. `getpass` prompts for the password (never echoed to screen or stored in shell history). OAuth tokens are cached in `~/.garminconnect/` (~1 year validity). The password is used once and then discarded.
2. **Sync** (default): Uses cached tokens only — no credentials needed. Token refresh is automatic (OAuth1 → OAuth2 exchange, no password required). If tokens expire or are revoked by Garmin, re-run setup.
