# Balanced 180 Coverage Repair v3 Results

## Runtime Contract

- Fixed IDs from `balanced-180-v51-fixed.json`, six types, 30 episodes per type.
- Runtime received history, timestamps, question, and question date only.
- No `question_type`, `_abs` inspection, gold memory tags, embeddings, reranker, or forced Reader route.
- Unified `orchestrator-ledger-catalog` loop with parent and Fork limits of 10 turns.
- Model `glm-5.2`, completion budget 4096, context budget 12,000 characters.
- v3 split factual packet validity from coverage completeness, added one bounded coverage-repair
  Fork/Compile phase, tightened cardinality Guard behavior, and made preference contracts
  constraints-only.

## Generation Integrity

- Final artifact contains 180 rows, 180 unique manifest IDs, and 30 episodes per type.
- All 180 final rows have `status=completed`; no infrastructure error row was judged.
- Three-way generation concurrency caused TokenHub timeouts and was abandoned.
- Failed episodes were rerun in fresh output directories because the current evaluation runner's
  `--resume` path reuses the episode memory directory and memory formation is not idempotent.
- Seventeen infrastructure-affected or resume-contaminated episodes were regenerated in a fresh
  directory at concurrency 1 with a 300-second per-request timeout.

## Independent Judge

Independent `glm-5.2` judging scored 156/180 = **86.67%**.

| Question type | v51 | v2 clean | v3 | Delta vs v51 | Delta vs v2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single-session assistant | 30/30 | 30/30 | 29/30 | -1 | -1 |
| Single-session preference | 29/30 | 26/30 | 28/30 | -1 | +2 |
| Single-session user | 29/30 | 29/30 | 29/30 | 0 | 0 |
| Knowledge update | 27/30 | 27/30 | 27/30 | 0 | 0 |
| Temporal reasoning | 26/30 | 27/30 | 24/30 | -2 | -3 |
| Multi-session | 21/30 | 19/30 | 19/30 | -2 | 0 |
| **Overall** | **162/180** | **158/180** | **156/180** | **-6** | **-2** |

Against v51 on the same IDs, v3 had 5 improvements and 11 regressions. Against v2 clean, v3 had
12 improvements and 14 regressions. The selected 11-ID v51-to-v2 regression gate scored 9/11 in
this full run, compared with 10/11 in the earlier targeted run. The two unstable IDs were
`c4a1ceb8` and `gpt4_468eb063`.

## Runtime Observability

- Parent turns: 4.82 per episode, compared with 3.96 in v51.
- Child results: 366 total, or 2.03 per episode; v51 averaged 1.84 Forks per episode.
- Compiler calls: 217 total.
- Coverage-repair phase: 35/180 episodes (19.44%), scoring 27/35 = 77.14%.
- Child sidechains reaching max turns: 39 across 24 episodes; those episodes scored 15/24 = 62.5%.
- Compiler sidechains reaching max turns: 6; only 2/6 passed.
- At least one fact-valid child packet: 154 episodes, scoring 137/154 = 88.96%.
- No fact-valid child packet: 26 episodes, scoring 19/26 = 73.08%.
- Final Compiler coverage marked complete: 48 episodes, scoring 43/48 = 89.58%.
- Answer Guard applied: 50 episodes, scoring 48/50 = 96%; the tightened Guard is not the main
  source of the v3 regression.

## Failure Interpretation

1. **Coverage repair increases work but does not reliably recover missing facts.** It activated on
   35 episodes, not only rare edge cases. Hard episodes that triggered repair still scored 77.14%.
2. **Child completion remains the dominant bottleneck.** Multi-session had 9 episodes with a
   max-turn child and 5 of those failed. Several failures returned truncated or non-JSON reports
   after the child had located useful evidence.
3. **Compiler coverage is not a correctness certificate.** Complete Compiler coverage improved from
   36 episodes in v2 to 48 in v3, but 5 of the 48 still failed. Source exhaustion does not guarantee
   correct identity, category membership, date projection, or aggregation.
4. **Targeted regression recovery was not stable across fresh generations.** Citrus counting and
   the Emma temporal question passed the targeted run but failed this run because child reports and
   identity linkage changed. The earlier 10/11 result should not be treated as a promoted baseline.
5. **Latency grew materially.** v3 used more parent turns, children, and Compiler calls. Some complex
   episodes took 10-20 minutes at concurrency 1. Accuracy did not justify that cost.
6. **The remaining multi-session failures are mostly missing-census failures.** Clothing pickups,
   tanks, baking events, road-trip durations, weddings, movie festivals, bike spending, and sports
   events were undercounted or not found. More generic repair turns did not solve source selection.

## Decision

Do not promote v3 over v51 or v2. Keep the factual-validity/coverage split and the tightened
cardinality Guard because their local behavior is sound. Disable or redesign the automatic bounded
coverage-repair phase before the next full run.

The next experiment should be smaller and causal:

1. Add a hard per-episode model-call budget and deterministic early stopping.
2. Make child output schema completion reliable before increasing source scope.
3. Route a second child by missing evidence facet or missing source cluster, not merely by unresolved
   source refs.
4. Treat Compiler coverage as navigation state, then validate identity, set membership, temporal
   projection, and aggregation separately.
5. Fix evaluation resume so episode memory formation is idempotent before running another large job.

## Artifacts

- Generation: `../work/eval-runs/balanced180-coverage-repair-v3-merged/qa-agent-lab-clean.jsonl`
- Judge: `../work/eval-runs/balanced180-coverage-repair-v3-merged/judge-glm52-clean.jsonl`
- Judge summary: `../work/eval-runs/balanced180-coverage-repair-v3-merged/judge-glm52-clean.jsonl.summary.json`
- Analysis: `../work/eval-runs/balanced180-coverage-repair-v3-merged/analysis-clean.json`
- Fresh retry batch: `../work/eval-runs/balanced180-coverage-repair-v3-fresh-retry17/qa-agent-lab.jsonl`
