# Phase 2: Bundle-First Reader

## Goal

Improve evidence organization without embeddings or a reranker. The old reader
could retrieve the correct sessions but repeatedly injected full records, mixed
irrelevant sources into the prompt, and treated unsupported relation inferences
as countable facts.

## Implementation

- `EvidenceBundleCompiler` decomposes a query into lexical facets.
- Search results from the full query and individual facets are merged.
- Evidence is grouped by source and reduced to relevant user-text windows.
- The packet reports covered and uncovered facets explicitly.
- Evidence Reader receives the bounded packet first and retains
  `MemoryEvidenceBundle`, `MemorySearch`, and `MemoryRead` for progressive
  disclosure.
- A valid reader report prevents the parent from injecting the same full memory
  records again.
- Pending-action counts keep event identity separate from entity identity.
- Leadership counts require explicit predicate support; completing a project is
  not treated as proof that the user led it.
- Structured exclusions and approximate timeline boundaries are normalized
  without invalidating the fact ledger.

## Offline Source Coverage

Balanced diagnostic: five temporal, five multi-session, and five
knowledge-update episodes.

| Max sources | Mean source recall | Perfect recall rate | Mean bundle chars |
|---:|---:|---:|---:|
| 8 | 0.900 | 0.800 | 7,668 |
| 10 | 0.950 | 0.867 | 8,781 |
| 14 | 0.967 | 0.933 | 10,356 |

The reader therefore uses `14` as its current source cap. These source metrics
are diagnostics, not QA scores: LongMemEval can label a session as an answer
source even when it does not contain the query predicate verbatim.

Artifact: `work/eval-runs/evidence-bundle-balanced15-v1/summary.json`.

## Online Targeted Regression

The final clean run used `glm-5.2` for the agent and an independent `glm-5.2`
LongMemEval judge.

| Question | Previous failure | Final answer |
|---|---|---|
| `0a995998` | Merged clothing entities/actions and answered 2 | 3 pending actions |
| `6d550036` | Inferred leadership from project completion and answered 3 | 2 explicitly supported projects |
| `gpt4_59c863d7` | Provider-format failure | 5 model kits |

Final targeted SR: `3/3 = 1.00`.

Artifacts:

- `work/eval-runs/agent-lab-bundle-final3-v4/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-bundle-final3-v4/qa-judge-glm52.summary.json`

This is a targeted regression, not an aggregate benchmark claim. The next
online gate should be a fresh balanced temporal/multi-session batch before a
full 500-episode run.

## Fresh Balanced Gate: Offset 5

The next gate selected five previously unused `temporal-reasoning` episodes and
five previously unused `multi-session` episodes with `--offset 5`.

Before the online run, bounded answer-source-family expansion was added for
sources named like `answer_<episode>_<session>`. Lexical aliases cover narrow
vocabulary gaps such as doctor/physician/specialist without introducing an
embedding model or reranker. The resulting offline diagnostic reached `1.00`
mean source recall and `1.00` perfect-recall rate across the ten episodes, with
an average evidence bundle size of `9,868` characters.

The untouched online run completed all ten episodes without provider errors:

| Slice | Correct | SR |
|---|---:|---:|
| temporal-reasoning | 4 / 5 | 0.80 |
| multi-session | 4 / 5 | 0.80 |
| overall | 8 / 10 | 0.80 |

Both failures had complete, valid reader reports. The temporal failure found
the baking class on March 20 and the birthday cake on April 10, but the parent
answered their distances from the question date instead of the supported
21-day interval. The multi-session failure found all three plant acquisitions,
but treated an explicit "last month" statement as uncertain and answered two.

The evidence decision layer now derives these narrow answer contracts from the
structured ledger:

- `temporal_interval_days` applies only when an ambiguous query combines two
  dated events and the report explicitly records that they are separate.
- `event_entity_count` deduplicates completed acquisition events for explicit
  last-month acquisition questions.
- The question reference date is passed separately into the Evidence Reader so
  query cleanup no longer removes temporal context from the child agent.

Online failure regression after these changes scored `2/2`: the plant answer
was guarded to `3`, and the temporal answer was guarded to `21`. This is a
failure regression, not a claim that the entire post-fix batch was rerun at
`10/10`.

Artifacts:

- `work/eval-runs/evidence-bundle-fresh-balanced10-offset5-v2-family/summary.json`
- `work/eval-runs/agent-lab-fresh-balanced10-offset5-v1/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-fresh-balanced10-failures-v2/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-fresh-balanced10-temporal-v3/qa-judge-glm52.summary.json`

The next generalization gate should use another untouched offset with at least
ten temporal and ten multi-session episodes. A full 500-episode run should wait
until that gate preserves source recall and improves online SR without adding
question-specific rules.

## Balanced 100-Episode Gate: Offset 10

The larger gate selected 50 previously unused `temporal-reasoning` episodes and
50 previously unused `multi-session` episodes with `--offset 10`.

Offline evidence coverage remained high but was no longer perfect:

| Slice | Mean source recall | Perfect-recall rate |
|---|---:|---:|
| temporal-reasoning | 0.976 | 0.94 |
| multi-session | 0.940 | 0.84 |
| overall | 0.958 | 0.89 |

The untouched online run produced 95 completed answers and five repeatable
TokenHub `HTTP 400 messages` provider-format errors. The independent `glm-5.2`
judge used a 2,048-token output budget so reasoning tokens could not consume the
entire judge response.

| Slice | Official correct | Official SR | Completed-only accuracy |
|---|---:|---:|---:|
| temporal-reasoning | 41 / 50 | 0.82 | 41 / 48 = 0.854 |
| multi-session | 43 / 50 | 0.86 | 43 / 47 = 0.915 |
| overall | 84 / 100 | 0.84 | 84 / 95 = 0.884 |

Of the 11 completed QA failures, nine had perfect answer-source recall. Only
two failures had incomplete source recall. Retrieval is therefore no longer the
dominant error source in this cohort; reader interpretation, answer contracts,
and provider message handling dominate.

The run also exposed an over-broad `pending_action_count` guard. Any question
containing words such as `buy` or `cancel` was previously treated as a pending
obligation, even when it asked about a completed event. All four times that
guard fired in the untouched run, the answer was wrong. The guard now requires
explicit pending intent such as `need to`, `still have to`, `pending`, or `left
to`.

A targeted online regression after the fix scored `3/4`: all three temporal
questions recovered their correct answers (`18`, `10`, and `54` days), while a
furniture count remained wrong because its source recall was only `0.5`.
Replacing the four old results gives an equivalent cohort score of `87/100`,
but this is not reported as a clean post-fix full-batch score.

Artifacts:

- `work/eval-runs/evidence-bundle-balanced100-offset10-v1/summary.json`
- `work/eval-runs/agent-lab-balanced100-offset10-final/run-summary.json`
- `work/eval-runs/agent-lab-balanced100-offset10-final/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-balanced100-offset10-guard-regression-v2/qa-judge-glm52.summary.json`

The next engineering priorities are to fix the repeatable deep-tool-loop
provider serialization failure, keep deterministic guards predicate-specific
and opt-in, and improve source grouping for the remaining incomplete-recall
multi-session questions. Another full 100-episode run should follow those
changes before expanding to all 500 episodes.

## Role-Aware Assistant and Update Gate

The next reader extension targeted 30 `single-session-assistant` episodes and
30 `knowledge-update` episodes. Evidence snippets now preserve `user`,
`assistant`, or `unknown` speaker roles. Assistant-memory questions prefer
assistant-authored snippets, while all existing user-memory paths continue to
prefer user-authored snippets with cross-role fallback.

The evaluator now accepts `--forceReaderTypes`. The two new routes use distinct
objectives:

- `single-session-assistant` recovers prior assistant content without treating
  it as a user belief, action, or preference.
- `knowledge-update` builds an old-to-new state ledger and marks the older value
  as superseded instead of merging competing values.

Offline coverage on the 60-episode cohort was:

| Slice | Source recall | Role coverage |
|---|---:|---:|
| single-session-assistant | 0.900 | 0.900 |
| knowledge-update | 0.983 | 0.983 |
| overall | 0.942 | 0.942 |

The online run forced both types through the Evidence Reader. All 60 episodes
completed without provider errors, and the independent `glm-5.2` judge scored:

| Slice | Correct | SR |
|---|---:|---:|
| single-session-assistant | 30 / 30 | 1.00 |
| knowledge-update | 30 / 30 | 1.00 |
| overall | 60 / 60 | 1.00 |

All 30 assistant reports were valid. Twenty-seven of 30 knowledge-update
reports were valid; the parent still produced judge-correct answers on the
three invalid-report cases. Three assistant questions and one update question
had incomplete initial source coverage, but progressive disclosure through
`MemoryEvidenceBundle`, `MemorySearch`, and `MemoryRead` recovered the needed
evidence online.

The first online configuration allowed 14 initial assistant sources and
truncated every assistant bundle. A post-run rank analysis found every initially
retrieved answer source within the top seven. Reducing the assistant-only cap to
eight preserved source and role coverage at `0.900` while reducing mean bundle
size from approximately `25.4k` to `19.6k` characters. Other question types
retain the 14-source cap.

Artifacts:

- `work/eval-runs/evidence-bundle-assistant-update60-role-v3-preferred/summary.json`
- `work/eval-runs/evidence-bundle-assistant30-role-max8-v1/summary.json`
- `work/eval-runs/agent-lab-assistant-update60-role-final/run-summary.json`
- `work/eval-runs/agent-lab-assistant-update60-role-final/qa-judge-glm52.summary.json`

This is a successful treatment run, not a causal A/B result. The same IDs were
not run through the old direct-context path. The next validation should use a
fresh offset and compare direct context with the forced role/state reader on
identical IDs before attributing the score to the new architecture.

## Unseen-Offset A/B, Preference, and Abstention Gate

A fresh 40-episode cohort used the next unseen offset: 20
`single-session-assistant` and 20 `knowledge-update` questions. The identical
IDs were run once with direct memory context and once with the forced Evidence
Reader, then judged by the same independent `glm-5.2` process.

| Route | Assistant | Update | Overall |
|---|---:|---:|---:|
| direct | 20 / 20 | 19 / 20 | 39 / 40 (0.975) |
| reader | 20 / 20 | 20 / 20 | 40 / 40 (1.000) |

The only paired transition was `2133c1b5`: direct extrapolated an old April
duration to seven months, while the reader selected the latest explicit
October state of three months. There were no reader regressions. The causal
gain is therefore positive but small: one episode, or 2.5 percentage points.
This supports selective routing for conflicting dated states rather than
forcing every assistant or update question through a child model.

The A/B run also exposed three child repair requests that sent
`tool_choice: auto` while no tools were available. The parent fallback still
answered those episodes correctly. The OpenAI-compatible adapter now omits
both `tools` and `tool_choice` when the filtered tool list is empty.

The first full preference run scored `29/30` (0.967). Its only failure did not
recover the user's prior portable-power-bank context and returned generic phone
battery advice. Evidence reports were valid in 25 episodes; three child runs
hit the pre-fix empty-tool provider error, while the parent recovered judge-
correct answers in those cases.

The initial 30 `_abs` run scored `26/30` (0.867):

| Slice | Correct | SR |
|---|---:|---:|
| single-session-user | 6 / 6 | 1.000 |
| multi-session | 9 / 12 | 0.750 |
| temporal-reasoning | 6 / 6 | 1.000 |
| knowledge-update | 5 / 6 | 0.833 |

The reader marked 29/30 reports as `no_answer`, but the parent ignored that
decision in three failures and one episode ended with an empty answer. The
failures were relation and provenance violations: thesis research was treated
as an undergrad course project, Senior Software Engineer as Software Engineer
Manager, and an assistant-estimated bus price as a user-provided fact.

The runtime now enforces a sourced `no_answer` contract whenever the reader
report is valid or contains explicit missing-information entries. It replaces
parent inference or empty output with a concise evidence-grounded abstention.
All four original failures passed a targeted online rerun and independent
judge (`4/4`). Substituting those reruns gives an equivalent `30/30`, but it is
not reported as a clean full-batch post-fix score.

Artifacts:

- `work/eval-runs/agent-lab-ab40-direct-final/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-ab40-reader-final/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-preference30-final/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-abs30-final/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-abs4-noanswer-guard-v1/qa-judge-glm52.summary.json`

The next clean gate should rerun all 30 abstention episodes after the guard,
then compare selective and forced reader routing on a mixed unseen cohort. The
route should trigger on explicit state conflicts, temporal operands, uncovered
facets, or provenance-sensitive comparisons; easy direct questions should not
pay the child-agent latency cost.

## Unified Six-Type 120-Episode Gate

The current code was evaluated under one protocol across all six standard
LongMemEval question types, with 20 episodes per type and the corresponding
Evidence Reader workflow forced for every episode. The selection preferred IDs
absent from every local `qa-agent-lab.jsonl` artifact. This produced 86 unseen
episodes and 34 current-version reruns: only six assistant episodes remained
unseen, and all 20 preference episodes were reruns.

The first generation pass completed 117/120 episodes (`0.975`). Two temporal
episodes and one update episode hit TokenHub `HTTP 400 messages` errors. Both
temporal episodes recovered on the first resume. The update episode was
repeatably sensitive to the long tool/message sequence and required additional
resumes. The final judged set contains 120 completed answers; five provider
errors occurred across all attempts.

The independent `glm-5.2` judge scored 111/120 (`0.925`):

| Type | Correct | SR | Initial source recall | Valid reports | Mean child turns | Guards |
|---|---:|---:|---:|---:|---:|---:|
| single-session-user | 20 / 20 | 1.00 | 1.000 | 20 / 20 | 2.25 | 0 |
| single-session-assistant | 20 / 20 | 1.00 | 0.900 | 20 / 20 | 2.25 | 0 |
| single-session-preference | 17 / 20 | 0.85 | 0.800 | 19 / 20 | 3.85 | 3 |
| temporal-reasoning | 18 / 20 | 0.90 | 0.775 | 17 / 20 | 3.50 | 1 |
| multi-session | 17 / 20 | 0.85 | 0.950 | 18 / 20 | 2.90 | 0 |
| knowledge-update | 19 / 20 | 0.95 | 0.950 | 16 / 20 | 2.75 | 0 |

Across all types, mean initial source recall was `0.896`, perfect source recall
was `0.858`, and 110/120 Reader reports were valid. Assistant questions reached
20/20 despite two initial answer-source misses, demonstrating successful
progressive disclosure. Multi-session reached only 17/20 despite `0.95` source
recall, so its remaining errors are predominantly interpretation and relation
resolution rather than retrieval.

The most important regression is the scope of the deterministic no-answer
guard. It fired four times on these standard questions and all four guarded
answers failed: three preference questions and one temporal question. Three of
those four had perfect initial answer-source recall. The Reader interpreted a
missing exact phrase or proper name as missing evidence even when the benchmark
accepted a supported preference or descriptive identity. The guard remains
useful for explicit `_abs` audits, but it should not be globally authoritative
on standard questions without a stronger coverage/entailment check or an
explicit opt-in mode.

The nine QA failures divide into:

- four false `no_answer` decisions amplified by the guard;
- one empty temporal answer with incomplete source recall and an invalid report;
- two multi-session answers that rejected benchmark-supported cross-session
  inference despite perfect source recall;
- one multi-session extraction/reasoning failure with `0.5` source recall;
- one update answer that preferred a verified value (`1250`) over the latest
  user estimate expected by the benchmark (`1300`).

Artifacts:

- `work/eval-runs/agent-lab-six-types20-current-v1/selection.json`
- `work/eval-runs/agent-lab-six-types20-current-v1/aggregate-summary.json`
- `work/eval-runs/agent-lab-six-types20-current-v1/<type>/qa-judge-glm52.summary.json`
- `work/eval-runs/agent-lab-six-types20-current-v1/<type>/evidence-diagnostic/summary.json`

The next change should make no-answer enforcement an explicit answerability-
audit policy rather than a default consequence of any Reader report. After
that change, rerun the four guarded standard failures and the 30 `_abs` set to
measure the precision/recall tradeoff before another full 120-episode gate.

## Full 500-Episode Completion Gate

The complete `longmemeval_s_cleaned` set was run with `glm-5.2` for generation
and an independent `glm-5.2` answer judge. The final artifact contains 500
unique question IDs, all with `status=completed`, non-empty hypotheses, and no
generation errors or missing IDs. All six question types and all 30 `_abs`
episodes are present.

The independent judge scored 465/500 (`0.930`):

| Type | Correct | SR |
|---|---:|---:|
| single-session-user | 67 / 70 | 0.957 |
| single-session-assistant | 56 / 56 | 1.000 |
| single-session-preference | 28 / 30 | 0.933 |
| temporal-reasoning | 123 / 133 | 0.925 |
| multi-session | 115 / 133 | 0.865 |
| knowledge-update | 76 / 78 | 0.974 |

The 470 standard episodes scored 435/470 (`0.9255`). All 30 abstention
episodes passed. The answer guard fired on those 30 `_abs` episodes and two
standard pending-action cases; all 32 guarded answers passed.

Reader reports were valid on 457/500 episodes. Valid-report episodes scored
433/457 (`0.9475`), while invalid-report episodes scored 32/43 (`0.7442`). Of
the 35 final QA failures, 24 had a valid Reader report and 11 had an invalid
report. The largest remaining category is therefore downstream evidence
interpretation and answer synthesis, not simply retrieval failure. Multi-
session remains the main weakness with 18 failures, followed by temporal with
10.

The run exposed and fixed several provider/context lifecycle defects:

- concurrent tool results could exceed TokenHub's accepted request shape;
- arbitrary truncation made structured tool results invalid JSON;
- deferred tool calls inserted a system message after a tool result;
- compression could remove every user-role message;
- resume treated `max_turns_exceeded` as completed;
- forced Reader completion still allowed the parent to enter another retrieval
  loop.

The final runtime keeps structured tool results parseable, preserves the latest
user request during compaction, supports provider-specific tool-call limits,
and separates the Reader evidence phase from a tool-free parent synthesis
phase. The regression suite now passes 45/45 tests.

This was an engineering completion gate rather than a fully frozen benchmark:
579 generation rows were produced across attempts, including 55 provider-error
rows and 15 `max_turns_exceeded` rows. Sixteen selected final episodes came
from adaptive retry paths after runtime fixes. The 0.930 score is valid for the
assembled current-system output, but a publication-grade comparison should
rerun all 500 episodes from scratch with the final configuration frozen.

Artifacts:

- `work/eval-runs/agent-lab-full500-current-v2/aggregate-summary.json`
- `work/eval-runs/agent-lab-full500-current-v2/final/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-full500-current-v2/final/qa-judge-glm52.jsonl`
- `work/eval-runs/agent-lab-full500-current-v2/final/failure-analysis.json`
- `work/eval-runs/agent-lab-full500-current-v2/initial-generation-summary.json`
