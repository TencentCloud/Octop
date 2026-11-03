# DeepXiv Workflows

Detailed playbooks. Use these alongside the decision table in `SKILL.md`.

## 1. Hot paper digest

Use when the user wants 热门论文 / 趋势综述 / 每周论文速递.

1. Pull a window:

```bash
deepxiv trending --days 7 --limit 10 --json
```

2. Brief each promising hit:

```bash
deepxiv paper <id> --brief
```

3. (Optional) Rank by social impact rather than citations:

```bash
deepxiv paper <id> --popularity
```

4. Pick the top 1–3 for deeper inspection:

```bash
deepxiv paper <id> --head
deepxiv paper <id> --section Introduction
deepxiv paper <id> --section Results
```

5. Produce a compact digest:
- 主题概览
- 每篇论文一句话总结
- 哪几篇最值得深入看，理由

## 2. Baseline comparison table

Use when the user wants 对比不同论文的方法 / 数据集 / 指标 / 成绩.

1. Narrow search with filters:

```bash
deepxiv search "long-context evaluation" \
  --categories cs.CL,cs.AI \
  --min-citations 30 \
  --date-from 2024-01-01 \
  --format json --limit 10
```

2. Brief every candidate; drop irrelevant ones immediately.

3. For survivors, read only what matters:

```bash
deepxiv paper <id> --section Method
deepxiv paper <id> --section Experiments
deepxiv paper <id> --section Results
```

4. Extract into a table or bullet list:
- paper (id + short title)
- task
- dataset
- metric
- reported score
- key method idea

5. Note explicitly which numbers came from which section, and flag any number you did not actually verify.

## 3. Single-paper explain

Use when the user gives one paper and wants a fast explanation.

1. `paper <id> --brief`
2. `paper <id> --head`
3. If still unsure where to look: `paper <id> --preview`
4. Then read the section most relevant to the question:

| Question type | Section |
|---------------|---------|
| What's the contribution? | `Introduction` |
| How does it work? | `Method` |
| Does it actually work? | `Experiments` / `Results` |
| What are the tradeoffs? | `Discussion` / `Limitations` |
| How does it relate to prior work? | `Related Work` |

5. Summarize, **stating which rung you stopped at**.

## 4. Author / project background check

Use when the user asks about an author, lab, project, or release — not a specific paper.

1. Web search first (cheap, broad):

```bash
deepxiv wsearch "<author or project name>" --json
```

2. If a relevant arXiv paper surfaces, climb the reading ladder on it.

3. For citation/co-author graph context:

```bash
deepxiv sc <semantic_scholar_id> --json
```

4. Report what you actually inspected vs. what is hearsay from web results.

## 5. Citation-aware literature scan

Use when the user wants 高影响力 / well-cited prior work, not the bleeding edge.

1. Search with a citation floor:

```bash
deepxiv search "<topic>" --min-citations 100 --format json --limit 10
```

2. Sort by citations:

```bash
deepxiv search "<topic>" --min-citations 100 --format json --limit 20 \
  | jq -r '.[] | "\(.citations // 0)\t\(.arxiv_id)\t\(.title)"' \
  | sort -k1 -n -r
```

3. Brief the top 5; read sections for the top 1–2.

## 6. Open-ended research question (agent fallback)

Use only when the question is genuinely multi-step, the user is okay with LLM cost, and manual `search` + `paper` flows would be unwieldy.

1. Make sure the user has already configured the agent's LLM backend on their side (via `deepxiv agent config`). Do not run setup yourself.

2. Ask:

```bash
deepxiv agent query "Compare retrieval-augmented vs long-context approaches for legal QA, with representative papers" --max-turn 10 --verbose
```

3. Verify any specific paper claims the agent makes by manually running `paper <id> --brief` or `--section` against them. The agent can hallucinate.
