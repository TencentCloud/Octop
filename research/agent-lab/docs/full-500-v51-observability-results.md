# Full 500 v51 Observability Results

## Runtime Contract

- Dataset: all 500 LongMemEval episodes, including 30 `_abs` episodes.
- Runtime input: history, timestamps, question, and question date only.
- No question type, `_abs` suffix check, embedding, reranker, or forced Reader route.
- Runtime profile: reconstructed `v51`, selected explicitly with `--runtimeProfile v51`.
- Loop: `orchestrator-ledger-catalog` with `TodoWrite`, `ForkSubagent`, ResultLedger, and `CompileEvidence`.
- Model: `glm-5.2`; parent and child limit: 10 turns; completion budget: 4096.
- Context compression: 12,000 characters, preserving 8,000 recent characters with a 2,500-character summary budget.

The original v51 label was an experiment artifact rather than a Git commit. The profile was reconstructed from its saved child and Compiler sidechains. Its schema 1.0 prompt, lack of automatic coverage repair, parent-visible Compiler packet, and answer-guard behavior are now explicit runtime choices.

## Generation Integrity

- 500 rows, 500 unique question IDs, 500 completed, 0 final errors.
- Six deterministic shards; all rows share one runtime configuration signature.
- One TokenHub HTTP 400 was recovered by an idempotent resume. Six interrupted attempts came from an intentionally stopped first run and remained visible in the attempt ledger.
- All 500 final rows contain timing, model-call, attempt, sidechain, ResultLedger, Compiler, guard, and context-compression observations.
- All 110 repository tests pass.

## Independent Judge

The comparable independent `glm-5.2` judge used the original 2,048-token completion budget.

| Question type | Correct | Total | SR |
| --- | ---: | ---: | ---: |
| Single-session preference | 29 | 30 | 96.67% |
| Single-session assistant | 54 | 56 | 96.43% |
| Single-session user | 65 | 70 | 92.86% |
| Temporal reasoning | 122 | 133 | 91.73% |
| Knowledge update | 71 | 78 | 91.03% |
| Multi-session | 97 | 133 | 72.93% |
| **Overall** | **438** | **500** | **87.60%** |

- Answerable episodes: 412/470 = 87.66%.
- Abstention episodes: 26/30 = 86.67%.
- On the exact prior balanced-180 IDs: 159/180 = 88.33%, versus the original v51 result of 162/180 = 90.0%.
- The three balanced-set differences were one fewer correct result each for multi-session, temporal reasoning, and single-session assistant. The other three types reproduced exactly.

## Observability

| Metric | Result |
| --- | ---: |
| Average parent turns | 3.966 |
| Average Forks | 1.886 |
| Average total model calls | 20.966 |
| Average episode wall time | 234.74 s |
| Compiler calls | 504 |
| Compiler repair attempts | 40 |
| Child reports | 942 |
| Structurally valid child reports | 474 (50.32%) |
| Structurally invalid child reports | 468 (49.68%) |
| Recoverable tool errors | 5 |

The control-flow signature closely matches the original balanced v51 run: 3.96 parent turns, 1.84 Forks, and 50.0% valid child reports.

Observed associations, not causal estimates:

- All child reports valid: 153/168 = 91.07%.
- At least one invalid child report: 285/332 = 85.84%.
- Compiler repair attempted: 31/40 = 77.50%.
- No Compiler repair: 407/460 = 88.48%.
- Answer guard applied: 12/16 = 75.0%.
- No answer guard: 426/484 = 88.02%.

## Judge Budget Finding

An initial diagnostic judge was accidentally limited to 128 completion tokens and scored 320/500 = 64.0%. Re-running the same hypotheses with the original 2,048-token budget scored 438/500 = 87.6%.

TokenHub keeps `reasoning_content` separate from answer text, but reasoning still consumes the completion budget. A tiny budget can therefore truncate judgment before a stable yes/no decision without leaking reasoning into the answer. The 128-token result is retained as a diagnostic artifact and must not be used as the experiment score.

## Conclusions

1. The v51 generic no-prior architecture generalizes to 87.6% on the complete 500-episode set.
2. Multi-session remains the dominant weakness at 72.93%; every other answerable type exceeds 91%.
3. Child schema validity is still only about 50%, and Compiler repair correlates with an 11-point lower SR. Schema reliability remains a high-value target.
4. The existing deterministic answer guard is not a universal improvement; guarded episodes scored 75%. Future guard changes require an explicit A/B rather than silent expansion.
5. Runtime and judge completion budgets are part of the experimental contract. They must be logged and held constant when comparing versions.

## Artifacts

- Merged generation: `../work/eval-runs/full500-v51-observability-merged/qa-agent-lab.jsonl`
- Attempt ledger: `../work/eval-runs/full500-v51-observability-merged/attempts.jsonl`
- Observability summary: `../work/eval-runs/full500-v51-observability-merged/run-summary.json`
- Final judge: `../work/eval-runs/full500-v51-observability-merged/judge-glm52-2k.jsonl`
- Final judge summary: `../work/eval-runs/full500-v51-observability-merged/judge-glm52-2k.jsonl.summary.json`
- Invalid low-budget diagnostic: `../work/eval-runs/full500-v51-observability-merged/judge-glm52.jsonl`
