# Full 500-Episode LongMemEval Results

## Executive Summary

Agent Lab completed the full `longmemeval_s_cleaned` dataset with 500 unique
episodes and no missing, empty, incomplete, or generation-error rows in the
final artifact. Generation used `glm-5.2`; answers were evaluated by a separate
`glm-5.2` judge process.

The final score was **465/500 (93.0% SR)**. The standard 470-question slice
scored **435/470 (92.55%)**, and all 30 abstention (`_abs`) questions passed.

## Results by Question Type

| Question type | Correct | Incorrect | SR |
|---|---:|---:|---:|
| single-session-assistant | 56 / 56 | 0 | **100.00%** |
| knowledge-update | 76 / 78 | 2 | **97.44%** |
| single-session-user | 67 / 70 | 3 | **95.71%** |
| single-session-preference | 28 / 30 | 2 | **93.33%** |
| temporal-reasoning | 123 / 133 | 10 | **92.48%** |
| multi-session | 115 / 133 | 18 | **86.47%** |
| **Overall** | **465 / 500** | **35** | **93.00%** |

Multi-session is the main remaining weakness. Its 18 failures account for
51.4% of all final errors. Multi-session and temporal reasoning together
account for 28/35 failures (80.0%). Assistant-attributed memory is currently
the strongest category, with no judged failures.

## Reader and Guard Diagnostics

| Slice | Correct | SR |
|---|---:|---:|
| Valid Reader report | 433 / 457 | **94.75%** |
| Invalid Reader report | 32 / 43 | **74.42%** |
| Guarded answers | 32 / 32 | **100.00%** |
| Guarded standard questions | 2 / 2 | **100.00%** |
| Guarded abstention questions | 30 / 30 | **100.00%** |

Reader validity is strongly associated with answer quality: valid reports
outperform invalid reports by 20.33 percentage points. Improving structured
Reader completion is therefore a meaningful optimization target.

However, 24 of the 35 final failures still had valid Reader reports. Retrieval
and evidence organization are not the whole problem. The parent answer stage
still needs better relation resolution, date arithmetic, benchmark-compatible
inference, and faithful use of the Reader ledger.

The no-answer guard was deliberately scoped to explicit abstention audits.
All 30 `_abs` cases passed. This does not justify enabling authoritative
no-answer enforcement for ordinary questions, where earlier experiments found
false abstentions when supported answers required accepted inference.

## Failure Distribution

| Question type | Failures | Share of failures |
|---|---:|---:|
| multi-session | 18 | 51.4% |
| temporal-reasoning | 10 | 28.6% |
| single-session-user | 3 | 8.6% |
| single-session-preference | 2 | 5.7% |
| knowledge-update | 2 | 5.7% |
| single-session-assistant | 0 | 0.0% |

Representative remaining error modes include:

- rejecting benchmark-supported cross-session inference even when the source
  evidence is present;
- confusing an event date, mention date, relative-time anchor, or inclusive
  boundary;
- omitting one item from an ordered event list;
- selecting the latest explicit state when the benchmark expects a different
  interpretation of the update sequence;
- producing a valid evidence report but not converting it into the concise
  answer expected by the judge.

## Generation Reliability

The assembled final artifact is clean, but reaching it exposed provider and
context-management failures:

| Metric | Value |
|---|---:|
| Final completed episodes | 500 / 500 |
| Total generation rows across attempts | 579 |
| Provider-error rows | 55 |
| Incomplete (`max_turns_exceeded`) rows | 15 |
| Unique IDs that encountered an error | 21 |
| Final episodes selected from adaptive retries | 16 |

The run led to fixes for oversized concurrent tool batches, invalid JSON after
tool-result truncation, invalid role ordering after deferred calls, loss of the
latest user message during compression, incorrect resume handling for
incomplete episodes, and parent retrieval loops after forced Reader completion.

The final runtime now keeps structured tool results parseable, supports a
provider-specific per-turn tool limit, preserves the latest user request during
compaction, retries every non-completed episode, and can run the final parent
answer phase without tools after Reader evidence collection.

## Interpretation and Limitations

This result is an **engineering completion gate**, not a publication-grade
frozen benchmark run. Runtime fixes and adaptive retry configurations were
introduced while completing difficult provider-sensitive episodes. The final
500-row artifact therefore measures the assembled current-system output, but
not one uninterrupted pass from a single immutable commit and configuration.

Additional limitations:

- generation and judging used the same model family, although they were
  separate calls with independent prompts;
- latency, token use, retry cost, and tool-call counts were not included in the
  final scorecard;
- SR is based on the independent LLM judge and should be accompanied by manual
  inspection of disputed or benchmark-ambiguous failures;
- the strongest next benchmark should rerun all 500 episodes from scratch from
  a frozen commit, provider profile, selection manifest, and context budget.

## Recommended Next Work

1. Freeze a provider capability profile instead of hard-coding TokenHub limits
   in the generic tool runtime.
2. Improve multi-session relation grouping and parent synthesis before adding
   more retrieval volume.
3. Add deterministic temporal normalization for event anchors, date intervals,
   and inclusive/exclusive counting.
4. Track latency, model calls, child turns, tool calls, context size, and retry
   count alongside SR.
5. Rerun a clean 500-episode benchmark from the frozen final implementation.

## Source Artifacts

The local evaluation artifact root is:

`work/eval-runs/agent-lab-full500-current-v2`

Key files:

- `aggregate-summary.json`
- `final/qa-agent-lab.jsonl`
- `final/qa-judge-glm52.jsonl`
- `final/generation-summary.json`
- `final/failure-analysis.json`
- `initial-generation-summary.json`

Large episode and judge artifacts are intentionally not committed to the source
repository. The aggregate metrics above are copied from
`aggregate-summary.json`.
