---
name: watchers
description: Poll RSS, JSON APIs, and GitHub with watermark dedup.
version: 1.0.0
author: Octop
license: MIT
compatibility: linux, macos
metadata:
  octop:
    label:
      zh: "订阅监控"
      en: "Watchers"
    summary:
      zh: "轮询 RSS、JSON API 与 GitHub，并按水位线去重。"
      en: "Poll RSS, JSON APIs, and GitHub with watermark dedup."
  harness:
    emoji: "🔔"
    tags: [cron, polling, rss, github, http, automation, monitoring]
    category: devops
    
    related_skills: []
---

# Watchers

## Harness-agent tools

This skill was ported from Octop. Use these harness/deepagents tools:

| Concept | Tool |
|---------|------|
| Shell | `execute` |
| Read / write / edit files | `read_file`, `write_file`, `edit_file` |
| Find files / search content | `glob`, `grep` |
| Fetch URLs | `web_fetch` |
| Browser automation | `browser_use` |
| Subagent work | `task` |
| Memory | `memory_store`, `memory_recall`, `memory_search` |

Builtin skill files live under `/_builtin_skills/<name>/`. User-installed skills live under `/skills/<name>/`.

Poll external sources on an interval and react only to new items. Three ready-made scripts plus a shared watermark helper; wire them into a cron job (or run them ad-hoc from the terminal).

## When to Use

- User wants to watch an RSS/Atom feed and be notified of new entries
- User wants to watch a GitHub repo's issues / pulls / releases / commits
- User wants to poll an arbitrary JSON endpoint and get notified on new items
- User asks for "a watcher for X" or "notify me when X changes"

## Mental model

A watcher is just a script that:

1. Fetches data from the external source
2. Compares against a watermark file of previously-seen IDs
3. Writes the new watermark back
4. Prints new items to stdout (or nothing on no-change)

The scripts below handle all three. The agent runs them via the execute tool — from a cron job, a webhook, or an interactive chat — and reports what's new.

## Ready-made scripts

All three live in `/_builtin_skills/watchers/scripts/` once the skill is installed. Each reads `WATCHER_STATE_DIR` (defaults to `watcher-state/`) for its state file, keyed by the `--name` argument.

| Script | What it watches | Dedup key |
|---|---|---|
| `watch_rss.py` | RSS 2.0 or Atom feed URL | `<guid>` / `<id>` |
| `watch_http_json.py` | Any JSON endpoint returning a list of objects | Configurable id field |
| `watch_github.py` | GitHub issues / pulls / releases / commits for a repo | `id` / `sha` |

All three:

- First run records a baseline — never replays existing feed
- Watermark is a bounded ID set (max 500) to cap memory
- Output format: `## <title>\n<url>\n\n<optional body>` per item
- Empty stdout on no-new — the caller treats that as silent
- Non-zero exit on fetch errors

## Usage

Run a watcher with `execute` (paths are relative to the workspace root after `init_workspace`):

```bash
python _builtin_skills/watchers/scripts/watch_rss.py \
  --name hn --url https://news.ycombinator.com/rss --max 5
```

Watch a GitHub repo (set `GITHUB_TOKEN` in the environment to avoid the 60 req/hr anonymous rate limit):

```bash
python _builtin_skills/watchers/scripts/watch_github.py \
  --name my-issues --repo owner/repo --scope issues
```

Poll an arbitrary JSON API:

```bash
python _builtin_skills/watchers/scripts/watch_http_json.py \
  --name api --url https://api.example.com/events \
  --id-field event_id --items-path data.events
```

## Periodic runs

octop-harness has no built-in cron. Options:

1. **Ad-hoc** — run a watcher when the user asks; summarize stdout if non-empty.
2. **OS cron / launchd** — schedule the same `python _builtin_skills/watchers/scripts/...` command on the host.
3. **External scheduler** — wire the script into your deployment's job runner.

Example user prompt:

> Every time I ask, run the HN watcher and summarize new headlines. Stay silent if stdout is empty.

## State files

Every watcher writes `watcher-state/<name>.json`. Inspect:

```bash
cat watcher-state/hn.json
```

Force a replay (next run treated as first poll):

```bash
rm watcher-state/hn.json
```

## Writing your own

All three scripts use the same template: load watermark, fetch, diff, save, emit. `scripts/_watermark.py` is the shared helper; import it to get atomic writes + bounded ID set + first-run baseline for free. See any of the three reference scripts for how little boilerplate it takes.

## Common Pitfalls

1. **Printing a "no new items" header every tick.** Callers rely on empty stdout = silent. If you print anything on an empty delta, you spam the channel. The shipped scripts handle this; custom scripts must too.
2. **Expecting the first run to emit items.** It won't — first run records a baseline. If you need an initial digest, delete the state file after the first run or add a `--prime-with-latest N` flag in your own script.
3. **Unbounded watermark growth.** The shared helper caps at 500 IDs. Raise it for high-churn feeds; lower it on constrained filesystems.
4. **Putting the state dir where the agent cannot write.** Default `watcher-state/` under the workspace is writable on the local backend.

