# Octop Memory — Agent Lab v51

Octop Memory is a long-term memory runtime for agents. This repository contains
the Agent Lab implementation used to develop and evaluate its evidence-oriented
memory workflow.

The runtime keeps Claude Code's central control flow:

```text
Model
  -> QueryStream
  -> ContextManager
  -> ToolOrchestration
  -> ToolExecution
  -> tool_result messages
  -> next model turn
```

For complex memory questions, the current frozen workflow adds explicit
evidence orchestration:

```text
Question
  -> Memory Catalog
  -> TodoWrite
  -> isolated read-only ForkSubagents
  -> ResultLedger
  -> CompileEvidence
  -> final answer
```

## Current Frozen LongMemEval Result

The current frozen benchmark baseline is the reconstructed `v51` runtime at commit
`a5fb5e6`. It completed the full 500-episode LongMemEval dataset and scored
**438/500 (87.60% SR)** with `glm-5.2` generation and a separate `glm-5.2`
judge call.

At runtime, every episode used the same `orchestrator-ledger-catalog` workflow.
The agent received conversation history, source timestamps, the question, and
the question date. It did not receive `question_type`, inspect `_abs`, use
embeddings or a reranker, or force an Evidence Reader route.

| Question type | Correct | Total | SR |
| --- | ---: | ---: | ---: |
| Single-session preference | 29 | 30 | 96.67% |
| Single-session assistant | 54 | 56 | 96.43% |
| Single-session user | 65 | 70 | 92.86% |
| Temporal reasoning | 122 | 133 | 91.73% |
| Knowledge update | 71 | 78 | 91.03% |
| Multi-session | 97 | 133 | 72.93% |
| **Overall** | **438** | **500** | **87.60%** |

The final artifact contains 500 unique completed rows and no final errors.
All rows share one runtime configuration signature and contain timing,
model-call, attempt, sidechain, ResultLedger, Compiler, guard, and context
compression observations.

| Runtime metric | Result |
| --- | ---: |
| Average parent turns | 3.966 |
| Average Forks | 1.886 |
| Average total model calls | 20.966 |
| Average episode wall time | 234.74 s |
| Compiler calls | 504 |
| Child reports | 942 |
| Structurally valid child reports | 474 (50.32%) |
| Recoverable tool errors | 5 |

See `docs/full-500-v51-observability-results.md` for the frozen protocol,
complete metrics, failure associations, judge-budget finding, and artifact
paths.

## Public Benchmark Context

Hy-Memory's public site reports **85.20%** on LongMemEval, compared with
68.32% for Graphiti and 47.00% for mem0. That disclosure used Kimi-K2.5 for
memory/answer generation and DeepSeek-V3.2 for judging, whereas Octop v51 used
`glm-5.2` for generation and a separate `glm-5.2` judge call.

Octop's 87.60% is therefore nominally 2.40 percentage points higher than the
published Hy-Memory headline, but this is not a controlled A/B. Model, judge,
prompt, context budget, retry policy, and public artifact availability differ.
Do not interpret the headline delta as a strict same-protocol ranking.

External values were checked on 2026-07-27:
<https://memory.hunyuan.tencent.com/>.

## Current Modules

- `src/core/messages.ts`: shared message, tool call, tool result, and event types.
- `src/core/tool.ts`: tool construction, schema validation, and tool lookup.
- `src/core/tool-execution.ts`: schema validation, semantic validation, permission checks, execution, and result truncation.
- `src/core/tool-orchestration.ts`: serial/concurrent tool batching for one assistant turn.
- `src/core/permissions.ts`: allow/deny/pass-through permission primitives plus path-scoped file permissions.
- `src/core/agent-loop.ts`: the thin model loop that delegates tool work to orchestration.
- `src/core/query-stream.ts`: the event stream that alternates model turns and tool turns.
- `src/core/context-manager.ts`: the model-input preparation boundary.
- `src/core/model-stream.ts`: streaming assembly with strict answer/reasoning/tool-input channels.
- `src/core/hooks.ts`: typed pre-tool, post-tool, and error lifecycle hooks.
- `src/core/context-compression.ts`: message canonicalization, pair-safe compaction, tool receipts, and structured working state.
- `src/adapters/tokenhub-stream.ts`: maps TokenHub `content`, `reasoning_content`, and tool deltas without mixing them.
- `src/core/mock-model.ts`: deterministic scripted model for tests.
- `src/tools/read-file.ts`: read-only file tool.
- `src/tools/write-file.ts`: file write tool gated by permissions.
- `src/memory/store.ts`: MemoryRecord V2 storage with immutable evidence, derived event/state/topic records, revisions, and audit log.
- `src/memory/tools.ts`: restricted memory search/read/create/update/delete tools.
- `src/memory/context-manager.ts`: relevance selection, source clustering, token-budget proxy, and structured evidence packets.
- `src/memory/evidence-reader-subagent.ts`: isolated read-only child agent for temporal, multi-session, conflict, and counting evidence.
- `src/memory/evidence-report.ts`: validates reader ledgers and derives narrow, provenance-backed answer decisions.
- `src/memory/memory-curator.ts`: isolated post-turn child agent that writes, defers, retrieves, or discards durable memory candidates.
- `src/memory/runtime.ts`: config-driven assembly of the memory agent.

## Run

```bash
npm test
npm run demo
npm run memory-demo
npm run eval:lme:smoke -- --model glm-5.2 --perType 1

# The evaluation defaults to a 4096-token completion budget so reasoning_content
# does not crowd out structured child and compiler JSON.

# Frozen v51 workflow. Run one deterministic shard with shardIndex 0-5.
npm run eval:lme:smoke -- \
  --model glm-5.2 \
  --all true \
  --routingMode orchestrator-ledger-catalog \
  --runtimeProfile v51 \
  --readerMode off \
  --maxTurns 10 \
  --forkMaxTurns 10 \
  --contextMaxChars 12000 \
  --contextPreserveRecentChars 8000 \
  --contextSummaryMaxChars 2500 \
  --maxTokens 4096 \
  --shardCount 6 \
  --shardIndex 0

# Strict blind evaluation: no question_type, _abs routing, or gold-label memory tags.
# The common Agent Loop decides whether to call ForkEvidenceReader.
npm run eval:lme:smoke -- --routingMode blind --model glm-5.2 --all

# Deterministic parallel shards use zero-based indexes and preserve the same sample set.
npm run eval:lme:smoke -- --routingMode blind --model glm-5.2 --all --shardCount 4 --shardIndex 0
npm run eval:lme:bundle -- --perType 5 --maxSources 14
npm run eval:lme:smoke -- --types temporal-reasoning,multi-session --perType 5 --offset 5
npm run eval:lme:smoke -- --types single-session-assistant,knowledge-update --perType 30 --forceReaderTypes single-session-assistant,knowledge-update
```

See `docs/longmemeval-data-flow.md` for the benchmark pipeline,
`docs/phase-2-reader-results.md` for the bundle-first reader results, and
`docs/full-500-v51-observability-results.md` for the current frozen result.

## LongMemEval Evaluation Guide

### 1. Install Octop Memory Agent Lab

Use a recent Node.js release with native `fetch`, then install dependencies and
run the deterministic test suite:

```bash
cd agent-lab
npm install
npm test
```

### 2. Prepare LongMemEval

The evaluator defaults to a sibling checkout at
`../LongMemEval/data/longmemeval_s_cleaned.json`. Download the official cleaned
dataset there, or pass any local dataset explicitly with `--data`.

```bash
cd ..
git clone https://github.com/xiaowu0162/LongMemEval.git
mkdir -p LongMemEval/data
cd LongMemEval/data
wget https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
cd ../../agent-lab
```

### 3. Configure the model endpoint

The runner accepts TokenHub or any OpenAI-compatible streaming endpoint. Never
commit the real API key.

```bash
export MEMORY_TREE_API_KEY="<your-api-key>"
export MEMORY_TREE_BASE_URL="https://tokenhub.tencentmaas.com/plan/v3"
export MEMORY_TREE_MODEL="glm-5.2"
```

`OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` are accepted as
fallback environment variables.

### 4. Run a smoke test

This command runs two temporal and two multi-session episodes with the
bundle-first Evidence Reader:

```bash
npm run eval:lme:smoke -- \
  --data ../LongMemEval/data/longmemeval_s_cleaned.json \
  --out ../work/eval-runs/lme-smoke \
  --model glm-5.2 \
  --types temporal-reasoning,multi-session \
  --perType 2 \
  --readerMode bundle \
  --forceReaderTypes temporal-reasoning,multi-session
```

For a balanced six-type run, use the complete type list and choose the number
of examples per type:

```bash
npm run eval:lme:smoke -- \
  --data ../LongMemEval/data/longmemeval_s_cleaned.json \
  --out ../work/eval-runs/lme-six-type-20 \
  --model glm-5.2 \
  --types single-session-user,single-session-assistant,single-session-preference,temporal-reasoning,multi-session,knowledge-update \
  --perType 20 \
  --readerMode bundle \
  --forceReaderTypes temporal-reasoning,multi-session
```

Use `--offset N` for a fresh slice, or `--ids id1,id2` for exact episodes.
`--readerMode legacy` restores full-memory reader injection, while
`--readerMode off` disables the forced Reader for direct-vs-reader A/B tests.

### 5. Run all 500 episodes

`--all true` includes every standard and `_abs` abstention episode. Re-running
the same command with `--resume true` preserves completed rows and retries
errors or incomplete episodes.

```bash
npm run eval:lme:smoke -- \
  --data ../LongMemEval/data/longmemeval_s_cleaned.json \
  --out ../work/eval-runs/agent-lab-full500 \
  --model glm-5.2 \
  --all true \
  --readerMode bundle \
  --forceReaderTypes temporal-reasoning,multi-session \
  --resume true \
  --timeoutMs 180000
```

For provider stability, a full run may be split into processes with disjoint
`--ids` lists. Merge only one final completed row per `question_id` before
judging; do not average transient attempts or infer overall SR from individual
shard progress.

### 6. Inspect generated evidence bundles

This offline diagnostic does not call the answer model. It is useful for
checking source clustering and covered/uncovered query facets first:

```bash
npm run eval:lme:bundle -- \
  --data ../LongMemEval/data/longmemeval_s_cleaned.json \
  --out ../work/eval-runs/lme-bundle-diagnostic \
  --types temporal-reasoning,multi-session \
  --perType 5 \
  --maxSources 14
```

Each online run writes:

- `qa-agent-lab.jsonl`: one hypothesis and its observability fields per episode.
- `run-summary.json`: completion, error, model, Reader mode, and type counts.
- `episodes/`: per-episode memory stores and runtime configuration.

### 7. Score with the official independent Judge

Octop Memory Agent Lab generates hypotheses; SR comes from a separate LLM judge call. The
official LongMemEval evaluator currently supports `gpt-4o` and
`gpt-4o-mini`. Use the same cleaned file for generation and reference lookup.

```bash
cd ../LongMemEval
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lite.txt
export OPENAI_API_KEY="<your-openai-api-key>"

python3 src/evaluation/evaluate_qa.py gpt-4o \
  ../work/eval-runs/lme-six-type-20/qa-agent-lab.jsonl \
  data/longmemeval_s_cleaned.json

python3 src/evaluation/print_qa_metrics.py \
  ../work/eval-runs/lme-six-type-20/qa-agent-lab.jsonl.eval-results-gpt-4o \
  data/longmemeval_s_cleaned.json
```

The first command writes
`qa-agent-lab.jsonl.eval-results-gpt-4o`; the second prints overall accuracy,
task-averaged accuracy, abstention accuracy, and SR for all six question types.

## Memory Flow

```text
user query
  -> canonicalize assistant tool_use / tool_result pairs
  -> compile old turns into a structured working_state
  -> summary search
  -> source-diverse selection
  -> full records with source + temporal metadata
  -> bounded <memory_context> packet
  -> final post-injection budget check
  -> model turn
  -> memory CRUD tools when state must change
  -> optional isolated memory curator
  -> evidence / events / state / topics + audit.jsonl
```

The canonical conversation never stores injected context. It is rebuilt for each
model turn, so stale retrieval does not become permanent conversation history.

The curator is off by default so existing evaluation runs remain a stable
baseline. Enable it in `memory-agent.config.json`, or set `curateAfterRun: true`
for a single `agent.run(...)` call. It receives a forked transcript, a separate
context budget, and only `MemorySearch`, `MemoryRead`, `MemoryCreate`,
`MemoryUpdate`, and `MemoryDeleteDerived`.

## Reader Experiments

`MemoryEvidenceBundle` performs query-facet lexical searches, groups results by
source, and exposes compact user excerpts plus covered and uncovered facets. It
does not use embeddings or a reranker. The Evidence Reader uses this bundle as
its first context and asks for more evidence only when coverage is incomplete.

The online evaluator supports reproducible variants:

```bash
# New bundle-first reader
npm run eval:lme:smoke -- --readerMode bundle --ids 0a995998,6d550036

# Previous full-memory-injection reader
npm run eval:lme:smoke -- --readerMode legacy --ids 0a995998,6d550036

# Parent agent without a forced reader
npm run eval:lme:smoke -- --readerMode off --ids 0a995998,6d550036
```

Curator formation can be observed separately with `--curator true`. It should
not be interpreted as a same-turn QA improvement because curation runs after
the parent answer.
