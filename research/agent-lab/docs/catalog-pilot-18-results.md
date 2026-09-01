# Catalog + Generic Fork Pilot (18 Episodes)

## Experiment contract

- Branch: `experiment/generic-fork-subagent`
- Dataset: LongMemEval, six question types, three fixed episodes per type
- Runtime input: history, timestamps, question, and question date only
- No runtime `question_type`, `_abs` suffix check, embedding, or reranker
- Unified parent loop: `TodoWrite -> ForkSubagent -> ResultLedger -> CompileEvidence`
- Memory layers: immutable Raw Memory, Frontmatter navigation, Event Ledger facts, query-scoped Evidence Result
- Model and independent judge: `glm-5.2`
- Parent/child turn limits: 10/10
- Parent context budget: 12,000 characters

## Judge result

| Type | Correct | SR |
| --- | ---: | ---: |
| knowledge-update | 2/3 | 66.67% |
| multi-session | 2/3 | 66.67% |
| single-session-assistant | 2/3 | 66.67% |
| single-session-preference | 2/3 | 66.67% |
| single-session-user | 2/3 | 66.67% |
| temporal-reasoning | 2/3 | 66.67% |
| **Overall** | **12/18** | **66.67%** |

All 18 runtime episodes and all 18 independent judge calls completed without fatal errors.

## Runtime observations

- Average parent turns: 7.83; maximum: 10
- Context compression activated: 18/18
- Parent calls: 33 `ForkSubagent`, 15 `CompileEvidence`, 11 `TodoWrite`
- Result Ledger entries: 33
- Strictly valid Evidence Results: 26/33 (78.79%)
- Complete coverage reports: 21/33 (63.64%)
- Failed child runs: 1/48; failed compiler runs: 0/15
- Three failed episodes exhausted 10 parent turns with reasoning deltas but no visible answer or tool call

## Failure diagnosis

1. **Reasoning-only loop stall (3 episodes).** Multi-session `2311e44b`, assistant recall `7161e7e2`, and preference `09d032c9` made no tool calls. The provider repeatedly spent the output budget on `reasoning_content`; the loop retried, but never converted that state into an action or bounded final answer.
2. **Evidence found, parent synthesis too conservative (1 episode).** Knowledge update `1cea1afa` recovered the latest value, 600, but weakened the direct answer with an unnecessary claim that the current value was unavailable.
3. **User fact versus plausible inference (1 episode).** Single-session user `6ade9755` found both Serenity Yoga and home practice, but preferred the more explicitly worded home statement over the benchmark's intended studio answer.
4. **Long cross-source compilation exceeded orchestration budget (1 episode).** Temporal `gpt4_7abb270c` recovered most museum evidence, but one child hit its turn limit and the parent started additional forks after compilation instead of producing the ordered list.

## Gate decision

Do not expand this version to 6 x 10 or 6 x 30 yet. It passes completion, compiler stability, context compression, and mean-parent-turn gates, but fails the 90% structured-result-validity gate and exposes a general reasoning-only recovery defect.

The next controlled experiment should change only generic loop behavior:

1. Bound consecutive reasoning-only retries and escalate the next turn to an explicit action-or-answer recovery instruction without exposing reasoning as answer content.
2. Reserve a final synthesis turn after a successful `CompileEvidence`; do not allow broad new forks unless the compiler explicitly reports a missing required facet.
3. Keep the answer contract direct: give the latest supported value first, then attach uncertainty without negating it.
4. Re-run the same 18 IDs before selecting unseen episodes.
