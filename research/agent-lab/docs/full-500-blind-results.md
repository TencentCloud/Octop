# Strict Blind 500-Episode LongMemEval Evaluation

## Protocol

This run measures the Memory Agent without benchmark-provided routing priors.
During answer generation, the Agent received only:

- conversation history and speaker roles;
- source timestamps;
- the question;
- the question date.

The runtime did not receive `question_type`, inspect the `_abs` suffix, store
gold question-type tags, force `ForkEvidenceReader`, or enable an answer guard.
All six benchmark types used the same Agent Loop and tool set. Question type
and abstention status were used only after generation by the independent
answer judge and aggregate analysis.

Generation and judging both used `glm-5.2`, but judging was a separate model
call with the official LongMemEval type-specific answer rubric and no access
to memory, tool traces, or generation context.

## Results

The independent judge scored 308/500 (`0.616`), 31.4 percentage points below
the earlier type-aware engineering gate (`0.930`).

| Type | Blind | Type-aware | Delta |
|---|---:|---:|---:|
| single-session-user | 68/70 (97.14%) | 67/70 (95.71%) | +1.43 pp |
| single-session-assistant | 40/56 (71.43%) | 56/56 (100.00%) | -28.57 pp |
| single-session-preference | 17/30 (56.67%) | 28/30 (93.33%) | -36.67 pp |
| temporal-reasoning | 62/133 (46.62%) | 123/133 (92.48%) | -45.86 pp |
| multi-session | 60/133 (45.11%) | 115/133 (86.47%) | -41.35 pp |
| knowledge-update | 61/78 (78.21%) | 76/78 (97.44%) | -19.23 pp |
| **Overall** | **308/500 (61.60%)** | **465/500 (93.00%)** | **-31.40 pp** |

The 30 abstention episodes scored 27/30 (`0.900`) without `_abs` detection or
an answer guard.

## Runtime Behavior

Initial generation produced 495 completed answers and five non-empty-answer
failures. Frozen-configuration retries recovered all five; the final set has
500 unique completed, non-empty hypotheses and no provider errors. The final
artifact records the five retry-sourced IDs separately.

- The Agent autonomously called `ForkEvidenceReader` on 6/500 episodes (1.2%).
- No answer guard fired.
- Average generation length was 6.674 turns.
- 144 episodes finished before the reserved final-answer turn and scored
  139/144 (`0.9653`).
- 356 episodes exhausted the normal tool budget and scored 169/356 (`0.4747`).
- The simple `MemorySearch -> MemoryRead` path scored 111/113 (`0.9823`).
- Seven repeated `MemorySearch` calls scored 12/33 (`0.3636`).

The dominant failure is therefore not ordinary single-record retrieval.
Simple questions are already strong. Performance collapses when the parent
must recognize that evidence spans sources, dates, speakers, conflicting
states, or multiple requested operands, and must decide to delegate evidence
organization instead of repeating lexical search.

## Next Experiment

The next module should be a question-and-state risk analyzer, not an oracle
six-class label injector. It should inspect only the question, question date,
retrieval coverage, source count, date spread, conflicts, and repeated tool
signatures. Its output should be a small operational decision such as:

- direct answer from one source;
- search and read one record;
- delegate multi-source evidence organization;
- audit answerability before answering.

This keeps the benchmark blind while giving the Agent an explicit way to
detect when its current retrieval path is not converging.

## Artifacts

- `work/eval-runs/agent-lab-full500-blind-v1/aggregate-summary.json`
- `work/eval-runs/agent-lab-full500-blind-v1/initial-generation-summary.json`
- `work/eval-runs/agent-lab-full500-blind-v1/final/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-full500-blind-v1/final/qa-judge-glm52.jsonl`
- `work/eval-runs/agent-lab-full500-blind-v1/final/generation-summary.json`
- `work/eval-runs/agent-lab-full500-blind-v1/final/failure-analysis.json`
