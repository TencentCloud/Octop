---
name: samsung-health
description: Analyze Samsung Health Connect data synced to Google Drive. Use for health tracking queries like sleep analysis, step counting, heart rate monitoring, SpO2 blood oxygen, workout history, and daily health reports. Requires Samsung Galaxy Watch/Ring with Health Connect backup to Google Drive enabled.
metadata:
  clawdbot:
    requires:
      bins: ["gog", "python3"]
    install:
      - id: clone
        kind: shell
        label: "Clone repository"
        command: "git clone https://github.com/mudgesbot/samsung-health-skill.git"
      - id: venv
        kind: shell
        label: "Create virtualenv and install"
        command: "cd samsung-health-skill && python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
---

# Samsung Health Connect CLI

Analyze health data from Samsung Health Connect exported to Google Drive.

## Prerequisites

- Samsung Galaxy Watch or Galaxy Ring with Samsung Health
- Samsung Health Connect app with Google Drive backup enabled
- `gog` CLI for Google Drive access (part of Clawdbot)

## Installation

```bash
cd /path/to/workspace/projects
git clone https://github.com/mudgesbot/samsung-health-skill.git
cd samsung-health-skill
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

Create `~/.config/samsung-health/config.yaml`:

```yaml
google_drive:
  folder_id: "YOUR_FOLDER_ID"      # From Google Drive URL
  account: "your.email@gmail.com"  # Google account for gog CLI
  file_name: "Health Connect.zip"

goals:
  daily_steps: 10000
  sleep_hours: 8

timezone: "Europe/Copenhagen"
```

## Commands

All commands require activating the venv first:
```bash
cd /path/to/samsung-health-skill && source .venv/bin/activate
```

### Sync Data
```bash
shealth sync              # Download latest from Google Drive
shealth sync --force      # Force re-download
```

### Quick Daily View
```bash
shealth today             # Today's snapshot (steps, sleep, HR, SpO2)
```

### Status
```bash
shealth status            # Data freshness, record counts, date range
```

### Sleep Analysis
```bash
shealth sleep             # Last 7 days
shealth sleep --days 14   # Custom period
```
Shows: duration, stage breakdown (Light/Deep/REM/Awake), trends.

### Step Tracking
```bash
shealth steps             # Last 7 days
shealth steps --week      # Weekly view
shealth steps --month     # Monthly view
```
Shows: daily counts, goal progress, streaks.

### Heart Rate
```bash
shealth heart             # Last 7 days
shealth heart --days 14   # Custom period
```
Shows: average, min/max, daily trends.

### Blood Oxygen (SpO2)
```bash
shealth spo2              # Last 7 days
shealth spo2 --days 14    # Custom period
```
Shows: average, range, trend. Normal: 95-100%.

### Workouts
```bash
shealth workout           # Last 30 days
shealth workout --days 90 # Custom period
```
Shows: session count, duration, types (Walking, Running, Swimming, etc.)

### Health Report
```bash
shealth report            # Comprehensive 7-day summary
shealth report --days 14  # Custom period
```
Shows: Energy Score, sleep summary, activity, heart rate.

## JSON Output

Add `--json` flag to any command for machine-readable output:
```bash
shealth --json today
shealth --json sleep --days 7
shealth --json report
```

## Sleep Stage Codes

| Code | Stage |
|------|-------|
| 1 | Light Sleep |
| 4 | Deep Sleep |
| 5 | Awake |
| 6 | REM Sleep |

## Exercise Types

| Code | Type |
|------|------|
| 53 | Walking |
| 33 | Running |
| 61 | Hiking |
| 21 | Cycling |
| 58 | Swimming |
| 4 | Weight Training |
| 66 | Yoga |

## Troubleshooting

**"Database not found"** — Run `shealth sync` first.

**"Google Drive not configured"** — Create config.yaml with folder_id and account.

**SpO2/HRV shows 0 records** — Requires Galaxy Watch 4+ or Galaxy Ring; may need enabling in Samsung Health settings.

## Source

GitHub: https://github.com/mudgesbot/samsung-health-skill
