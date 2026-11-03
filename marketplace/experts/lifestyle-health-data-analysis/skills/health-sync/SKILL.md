---
name: health-sync
description: Analyze synced health data across Oura, Withings, Hevy, Strava, WHOOP, and Eight Sleep.
homepage: https://github.com/filipe-m-almeida/health-sync
metadata:
  openclaw:
    emoji: "🩺"
    requires:
      bins:
        - node
        - npm
        - npx
      config:
        - workspace/health-sync/health-sync.toml
        - workspace/health-sync/.health-sync.creds
        - workspace/health-sync/health.sqlite
    install:
      - kind: node
        package: health-sync
        bins:
          - health-sync
read_when:
  - User asks for health-sync setup, auth, sync, provider status, or remote bootstrap onboarding
  - User asks about sleep, recovery, training, activity, your health, or cross-provider trends
---

# Health Sync Analysis Skill

## Purpose

This skill is dedicated to analyzing the user's health data across available providers:

- Oura
- Withings
- Hevy
- Strava
- WHOOP
- Eight Sleep

The main goal is to help the user understand trends, compare signals across providers, and find useful insights from their synced data.

## Scope

Use this skill when the user asks questions such as:

- How did I sleep last night?
- How was my last workout?
- How did my resting heart rate change during the year?
- What trends are you seeing in my recovery, sleep, and training?
- What useful insights or next steps should I focus on?

## Setup Handling (Remote Bootstrap Only)

Setup is bot-led and remote-first. The only supported onboarding flow is:

1. Bot runs `npx health-sync init remote bootstrap`.
2. Bot sends user: `npx health-sync init --remote <bootstrap-token>`.
3. User sends back encrypted archive.
4. Bot runs `npx health-sync init remote finish <ref> <archive>`.

For full operational instructions, always consult:

- `references/setup.md`

Do not use or recommend legacy direct setup flows such as:

1. `health-sync init` as the primary user instruction
2. `health-sync auth <provider>` as a standalone onboarding path

Those commands may still exist for maintenance/debugging, but they are not the setup flow this skill should guide.

## Runtime And Data Disclosure (Mandatory)

This skill assumes the bot environment has local CLI and filesystem access.

1. Required binary:
   - `node`
   - `npm`
   - `npx`
2. Expected local working paths:
   - `workspace/health-sync/health-sync.toml`
   - `workspace/health-sync/.health-sync.creds`
   - `workspace/health-sync/health.sqlite`
3. Sensitive-data handling:
   - Remote onboarding imports encrypted archives that contain provider credentials/tokens.
   - Finish flow writes decrypted secrets to local files on the bot host.
   - These files must be treated as sensitive at rest (access controls, backups, retention).
4. Chat-safety boundary:
   - Never ask users to paste raw secrets in chat.
   - Only collect encrypted archive files via remote bootstrap flow.

## Schema Handling

To understand data schemas and query correctly, read the provider reference files:

- `references/oura.md`
- `references/withings.md`
- `references/hevy.md`
- `references/strava.md`
- `references/whoop.md`
- `references/eightsleep.md`

## Freshness Rule (Mandatory)

Before any analysis, always run:

```bash
npx health-sync sync
```

If sync fails, report the failure clearly and continue analysis only if the user explicitly asks to proceed with potentially stale data.

## Analysis Workflow

1. Run `npx health-sync sync` first.
2. Identify the user question and which provider/resource(s) are relevant.
3. Read the provider schema reference before forming SQL.
4. Query `records`, `sync_state`, and `sync_runs` as needed.
5. Produce a clear, user-friendly answer with concrete numbers and dates.
6. Highlight meaningful patterns and offer practical guidance.
7. When data quality or coverage is limited, say so explicitly.

## Output Style

- Be concise, clear, and practical.
- Focus on useful interpretation, not just raw data dumps.
- Connect metrics to actionable insights (sleep, recovery, training, consistency, etc.).
- Ask follow-up questions only when necessary to improve analysis quality.
