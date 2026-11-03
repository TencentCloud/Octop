# financial-fraud-index

`financial-fraud-index` is a standalone agent skill for evidence-grounded analysis of annual reports and financial-fraud risk signals.

## What It Does

The skill helps an agent:

- read annual-report materials;
- identify confirmed anomalies, weak signals, and missing data;
- connect conclusions to excerpts and page-numbered evidence;
- avoid fabricated figures or unsupported claims.

## Install

Copy the `financial-fraud-index` folder into your agent skill directory.

Typical target locations:

- Codex-style environments: `~/.agents/skills/financial-fraud-index/`
- Claude Code-style environments: `~/.claude/skills/financial-fraud-index/`

## Package Contents

- `SKILL.md`: main operational instructions
- `examples/`: sample prompts and output shape
- `templates/`: reusable checklists and report outline
- `checks/`: manual release checklist

## Design Notes

- The skill is portable and does not require this repository.
- This repository can serve as a reference implementation for PDF extraction, risk scoring, and evidence formatting.
- The skill prioritizes source-grounded analysis over generic financial commentary.

## Minimum Operating Standard

The agent using this skill should:

- prefer primary report evidence;
- mark uncertainty explicitly;
- separate confirmed anomalies from weak signals;
- list missing data when confidence is limited.
