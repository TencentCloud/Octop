# Balanced 180 v51 Results

## Runtime Contract

- Six LongMemEval question types, 30 episodes per type, 180 total.
- The evaluator used labels only to construct the balanced sample.
- Each runtime episode received history, timestamps, the question, and question date only.
- No `question_type`, `_abs`, embedding, reranker, or forced Reader route was available to the Agent.
- All episodes used the same orchestrator-ledger-catalog loop with `TodoWrite`, `ForkSubagent`, ResultLedger, and `CompileEvidence`.
- Model: `glm-5.2`; completion budget: 4096; parent/fork max turns: 10.

## Generation Integrity

- Six deterministic shards, 30 episodes each.
- Initial run completed 175/180. Five infrastructure/orchestration failures were rerun with `--resume`; completed rows were preserved unchanged.
- Final merged artifact: 180 rows, 180 unique IDs, 180 completed, 0 empty answers.
- Episodes with a recoverable tool error: 3.
- Average parent turns: 3.96; average forks: 1.84.
- Child reports: 332 total, 166 structurally valid (50.0%).
- Episodes with at least one invalid child report: 114/180 (63.3%).
- Compiler calls: 181; conditional schema repairs: 17; deterministic count contracts: 6.

## Independent Judge

Independent `glm-5.2` judging scored 162/180 = **90.0%**.

| Question type | Correct | Total | SR |
| --- | ---: | ---: | ---: |
| Single-session assistant | 30 | 30 | 100.0% |
| Single-session preference | 29 | 30 | 96.67% |
| Single-session user | 29 | 30 | 96.67% |
| Knowledge update | 27 | 30 | 90.0% |
| Temporal reasoning | 26 | 30 | 86.67% |
| Multi-session | 21 | 30 | 70.0% |

## Failure Set

- Knowledge update: `031748ae`, `4d6b87c8`, `618f13b2`.
- Multi-session: `3a704032`, `46a3abf7`, `7024f17c`, `88432d0a`, `d23cf73b`, `dd2973ad`, `gpt4_2ba83207`, `gpt4_2f8be40d`, `gpt4_7fce9456`.
- Preference: `195a1a1b`.
- Single-session user: `3b6f954b`.
- Temporal: `9a707b81`, `gpt4_7abb270c`, `gpt4_7f6b06db`, `gpt4_e061b84f`.

Of the 18 judged failures:

- 16 had at least one invalid child report.
- 5 had a Compiler sidechain end with `max_turns_exceeded`.
- 6 attempted conditional Compiler repair.
- Only 1 had a parent-visible tool error.

## Failure Patterns

1. **Incomplete cross-source census**: plants, tanks, baking events, museums, and trips lost one or more valid sources before synthesis.
2. **State/update selection**: newer team-size or wear-count updates were missed or treated as unresolved conflicts.
3. **Boundary semantics**: “last month,” target-week inclusion, and whether the target property itself belongs in a pre-offer count were handled inconsistently.
4. **Identity and relation fidelity**: a wedding count was correct but the couples were wrong; one university answer collapsed to the city only.
5. **Correct evidence, weak final emphasis**: one temporal answer explicitly derived 21 days but led with an abstaining explanation, causing the judge to reject it.
6. **Compiler exhaustion**: five complex episodes had useful child evidence but no parseable final evidence packet.

## Conclusions

- The no-prior generic loop scales to 90% on a balanced 180-episode set without embeddings or a reranker.
- Raising the completion budget to 4096 materially improved structured report completion and preserved the fixed-gate gains.
- Multi-session remains the dominant weakness at 70%; the fixed 3/3 pilot overstated its generalization.
- The next optimization should target child-report schema reliability, source-coverage stopping criteria, and deterministic final-answer projection from compiled evidence.
- Do not add episode-specific retrieval vocabulary. The failures are primarily evidence lifecycle and synthesis failures, not lexical recall failures.

## Artifacts

- Generation: `../work/eval-runs/balanced180-v51-glm52-merged/qa-agent-lab.jsonl`
- Judge: `../work/eval-runs/balanced180-v51-glm52-merged/judge-glm52.jsonl`

