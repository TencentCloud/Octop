# Coverage Repair and Guard v3 Results

## Goal

Recover the fixed v51-to-v2 regression set without question-type priors, embeddings, reranking,
or episode-specific retrieval vocabulary.

## Implementation

- Split child evidence quality into two independent axes:
  - `fact_packet_valid`: candidate schema, provenance, and factual packet integrity.
  - `coverage_complete`: whether the assigned or discovered source scope is exhausted.
- Retained the legacy `evidence_result_valid` field for compatibility.
- Changed Compiler invalid-report accounting to reject fact-invalid packets without discarding a
  fact-valid packet merely because source coverage is incomplete.
- Added one bounded coverage-repair phase after the first parent answer draft:
  - only when Compiler coverage is incomplete and concrete unresolved source refs exist;
  - exactly one additional `ForkSubagent` and one additional `CompileEvidence` are allowed;
  - the child receives only the unresolved refs and read-only memory tools.
- Allowed a complete repair child to close an older unresolved source gap across ResultLedger records.
- Accepted memory IDs, source refs, and turn-level refs such as `source#turn-4` as navigation context.
- Restricted cardinality Guard replacement to complete, committed, internally consistent count contracts.
- Marked preference and recommendation contracts as `constraints_only`; the parent remains responsible
  for the user-facing recommendation.

## Verification

- TypeScript build passed.
- Unit and integration tests: 109/109 passed.
- The integration test exercises the full two-stage parent loop: Fork, Compile, draft, narrow Fork,
  re-Compile, final synthesis.

## Fixed Regression Gate

The gate contains the 11 IDs that v51 passed and schema/compiler v2 failed. Runtime still received no
`question_type`, `_abs` suffix, or gold memory tags.

| Type | v2 | v3 | Recovered |
| --- | ---: | ---: | ---: |
| Knowledge update | 0/1 | 1/1 | +1 |
| Multi-session | 0/5 | 4/5 | +4 |
| Single-session preference | 0/4 | 4/4 | +4 |
| Temporal reasoning | 0/1 | 1/1 | +1 |
| **Total** | **0/11** | **10/11** | **+10** |

The clean run used 24 child results and 13 Compiler calls. Two preference episodes triggered the
bounded coverage-repair phase. No Answer Guard fired and no tool error remained.

## Interpretation

- The correct postcard scalar (`01493427`) and total play time (`28dc39ac`) were preserved once the
  evidence-record count Guard stopped overriding scalar and aggregation answers.
- Preference recovered to 4/4 because evidence contracts remained personalization constraints and
  the parent generated the final advice.
- The narrow repair path activated selectively rather than adding a third Fork to every episode.
- The remaining failure, `gpt4_15e38248`, found the mattress evidence but treated whether a mattress
  belongs to the requested furniture category as uncertain. This is a general set-membership boundary
  problem; do not add a mattress-specific rule.

This selected gate demonstrates causal recovery, not overall SR. The next gate should include the seven
v2 improvements and a fresh balanced sample before running another 180 episodes.

## Artifacts

- Generation: `../work/eval-runs/regression11-coverage-repair-v3-merged/qa-agent-lab-clean.jsonl`
- Judge: `../work/eval-runs/regression11-coverage-repair-v3-merged/judge-glm52-clean.jsonl`
- Judge summary: `../work/eval-runs/regression11-coverage-repair-v3-merged/judge-glm52-clean.jsonl.summary.json`
