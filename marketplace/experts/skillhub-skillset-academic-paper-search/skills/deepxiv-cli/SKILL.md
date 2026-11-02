---
name: deepxiv-cli
description: Search, inspect, and progressively read open-access academic papers with the deepxiv CLI. Use when the user wants arXiv / PMC / Semantic Scholar paper search, paper triage, section-by-section reading, trending discovery, citation lookup, author background checks, baseline comparison, or literature review workflows without loading full papers too early.
---

# DeepXiv CLI

`deepxiv` is a progressive-reading paper tool for open-access literature (arXiv, PMC, Semantic Scholar) with optional web search and an LLM-powered research agent.

The single most important rule: **read the smallest amount of text that answers the question.** Climb the ladder only as far as needed.

## Progressive reading ladder

For any paper, prefer the cheapest rung that still answers the question:

| Rung | Command | What you get | When to use |
|------|---------|--------------|-------------|
| 1 | `paper <id> --brief` | Title, TLDR, keywords, citations, GitHub URL | First triage of any paper |
| 2 | `paper <id> --head` | Metadata + section list (JSON) | Decide which sections matter |
| 3 | `paper <id> --preview` | First ~10k chars (intro + early method) | Need more than TLDR but not full sections |
| 4 | `paper <id> --section <Name>` | One named section | Targeted answer (Method / Results / etc.) |
| 5 | `paper <id>` or `--raw` | Full markdown | Only when explicitly required |

Never jump to rung 5 unless the user asked for a full read or the task truly needs it.

## Setup

Before using `deepxiv`, verify it is available:

```bash
deepxiv --help
```

If missing, **stop and tell the user** — do not install it on your own. If the user asks you to install it, follow `references/install.md`, which has per-OS instructions, and only run install commands after the user explicitly approves them. `deepxiv` requires Python **3.10+**.

Health and diagnostics (safe to run any time):

```bash
deepxiv health     # API + token reachability check
deepxiv debug      # environment diagnostics
```

## Decision: which command do I want?

| User wants… | Start with |
|-------------|------------|
| "Find papers about X" | `search` (with filters if narrow) |
| "What's hot recently in X?" | `trending` |
| "Explain this paper" (has ID) | `paper --brief` → `--head` → section |
| "Compare these N papers" | `paper --brief` for each, then targeted sections |
| Biomedical / PubMed paper | `pmc <PMC_ID>` |
| Has only Semantic Scholar ID | `sc <id>` |
| "Who is this author / what's this project?" | `wsearch` |
| "Is this paper actually getting traction?" | `paper --popularity` |
| Open-ended multi-step research question | `agent query` (see caveats) |

## Core commands

### search — arXiv search with filters

```bash
deepxiv search "agent memory" --limit 5
deepxiv search "multimodal reasoning" --limit 10 --format json
```

Filters (combine freely):

```bash
# Category filter (arXiv categories)
deepxiv search "retrieval" --categories cs.IR,cs.CL --limit 5

# Date window
deepxiv search "diffusion" --date-from 2025-01-01 --date-to 2025-06-30

# Citation floor — useful to skip obscure preprints
deepxiv search "world model" --min-citations 50 --limit 5

# Search mode: hybrid (default), bm25 (literal), vector (semantic)
deepxiv search "chain of thought" --mode bm25 --limit 5
deepxiv search "models that can think before answering" --mode vector
```

Defaults:
- `--limit 3` to `5` for triage; raise only when explicitly needed
- `--format json` whenever you intend to post-process (pipe to `jq`)
- Use `bm25` for exact phrasing, `vector` for fuzzy concepts, `hybrid` otherwise

### paper — get an arXiv paper

```bash
deepxiv paper 2409.05591 --brief        # rung 1
deepxiv paper 2409.05591 --head         # rung 2
deepxiv paper 2409.05591 --preview      # rung 3
deepxiv paper 2409.05591 --section Method   # rung 4
deepxiv paper 2409.05591                # rung 5 — full
deepxiv paper 2409.05591 --popularity   # social impact / trending signal
deepxiv paper 2409.05591 --raw          # raw markdown (full)
```

Section names come from `--head`. Common names: `Introduction`, `Related Work`, `Method`, `Experiments`, `Results`, `Discussion`, `Limitations`, `Conclusion`. Names are paper-specific — do not guess; check `--head` first if unsure.

Use `--popularity` when the user asks "is this paper a big deal" or you need to rank by attention rather than citations.

### pmc — PubMed Central / biomedical

```bash
deepxiv pmc PMC544940 --head
deepxiv pmc PMC544940
```

PMC currently returns JSON only. Use when the target is biomedical or a PMC ID is given.

### sc — Semantic Scholar lookup

```bash
deepxiv sc 258001
deepxiv sc 258001 --json
```

Use when the user gives a Semantic Scholar ID, or when you need richer metadata (citation graph, author info) for an arXiv paper that you have already cross-referenced.

### trending — hot papers

```bash
deepxiv trending --days 7 --limit 10 --json
deepxiv trending --days 30 --limit 5
```

`--days` accepts only `7`, `14`, or `30`. Use for weekly digests and "what's hot" requests.

### wsearch — web search

```bash
deepxiv wsearch "karpathy"
deepxiv wsearch "DeepSeek R1 release notes" --json
```

Use for non-paper context: author background, project home pages, blog posts, release announcements. Cheap and broad — good for grounding before a paper read.

### agent query — LLM-powered research agent

```bash
deepxiv agent query "Compare RAG vs long-context for code QA"
deepxiv agent query "Latest agent memory papers" --max-turn 10 --verbose
```

This is a multi-turn research agent that can search and read papers on its own. Caveats:
- Requires the user to run `deepxiv agent config` once to set up their preferred LLM
- Consumes LLM usage on the user's account
- Slower and less predictable than manual `search` + `paper` flows
- Prefer manual progressive reading by default; reach for `agent query` only when the question is genuinely open-ended and the user has agreed to the cost

## JSON post-processing

When you need to slice search/trending output, prefer JSON + `jq` over re-running text searches:

```bash
deepxiv search "agent memory" --limit 10 --format json \
  | jq -r '.[] | "\(.arxiv_id)\t\(.citations // 0)\t\(.title)"' \
  | sort -k2 -n -r

deepxiv trending --days 7 --limit 20 --json \
  | jq -r '.[] | select(.categories[]? | test("cs\\.(AI|CL|LG)")) | .arxiv_id'
```

## Recommended workflows

### Topic exploration
"帮我找最近关于 agent memory 的论文":

1. `deepxiv search "agent memory" --limit 5 --format json` (add `--date-from` if "最近")
2. `paper <id> --brief` for each promising hit
3. Pick 1–2 for deeper reading

### Single paper explanation
"讲讲这篇论文 <id>":

1. `paper <id> --brief`
2. `paper <id> --head`
3. Read 1–2 sections most relevant to the question (or `--preview` if unsure)
4. Summarize, and **say which rung you stopped at**

### Baseline / comparison table
"帮我整理这个方向的 baseline":

1. Narrow search with `--categories` and optionally `--min-citations`
2. `--brief` every candidate
3. Read only `Method` / `Experiments` / `Results` for top picks
4. Extract: paper, task, dataset, metric, score, key idea

### Author / project background check
"这篇论文的作者还做过什么？" / "这个项目背景是什么？":

1. `deepxiv wsearch "<author or project>" --json`
2. If a related arXiv paper surfaces, climb the reading ladder on it
3. Optionally `sc <id>` for citation context

### Citation-aware filtering
"找有影响力的相关工作":

1. `deepxiv search "..." --min-citations 100 --format json`
2. Sort by citations via `jq`
3. Triage with `--brief`

### Hot digest
"本周热门论文":

1. `deepxiv trending --days 7 --limit 10 --json`
2. `--brief` the top picks
3. Optional `--popularity` to rank by attention
4. Compact digest: theme overview → one-line per paper → which to read deeper

See `references/workflows.md` for fuller versions of these.

## Output rules

- Always say which **rung** of the ladder informed your conclusion (e.g. "based on `--brief` only" vs. "after reading the Method section")
- Do not make section-level claims you didn't actually read
- Prefer concise bullet summaries when comparing multiple papers
- Keep context use low: small `--limit`, climb the ladder only as needed
- For literature reviews, prefer iterative narrowing over one giant search

## Common failure modes

**Auth or rate-limit issues** — run `deepxiv health` to check service reachability. If rate-limited or unauthorized, say so plainly and stop; do not silently retry.

**Paper not found** — verify ID format and source: arXiv (`2409.05591`), PMC (`PMC544940`), Semantic Scholar (`258001`). If unsure which, try `wsearch` first.

**Section name mismatch** — section names are paper-specific. Run `--head` to list real section names before `--section`.

**Over-reading** — do not jump to full text when `--brief`, `--preview`, or one section would do.

**Python 3.9 install** — `deepxiv` may install via pip but crash on first run. Switch to a Python 3.10+ environment.

## Good defaults

- `search --limit`: 3–5 for triage, 10 max
- `trending --limit`: 5–10
- Section reads per paper: 1–2 unless asked otherwise
- Full paper reads: opt-in only
- `agent query`: only for genuinely open-ended multi-step research, with user consent
