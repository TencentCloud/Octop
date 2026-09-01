# Balanced 180 Schema and Compiler v2 Results

## Runtime Contract

- Fixed IDs from `balanced-180-v51-fixed.json`, six types, 30 episodes per type.
- Runtime received history, timestamps, question, and question date only.
- No `question_type`, `_abs` inspection, embeddings, reranker, or forced Reader route.
- Unified `orchestrator-ledger-catalog` loop, parent raw-memory tools disabled.
- Model `glm-5.2`, 4096 completion tokens, parent and fork max turns 10.
- Compiler envelope bounded to 1,800 characters after a targeted compression failure was found.

## Generation Integrity

- Six shards produced 180 unique IDs matching the manifest exactly.
- Final generation state: 180 completed, 0 episode errors, 30 episodes per type.
- The initial six-way run overloaded TokenHub and created internal tool timeouts.
- Eight timeout-contaminated completed episodes were rerun at low concurrency; one Agent-generated
  unknown ResultLedger ID was retained because it is a real orchestration error.
- Both the raw artifact and the infrastructure-clean artifact are retained.

## Independent Judge

The raw run scored 155/180 = **86.11%**. Replacing only the eight timeout-contaminated rows and
rejudging only those rows produced 158/180 = **87.78%**. The fixed-ID v51 baseline was 162/180 =
**90.0%**.

| Question type | v51 baseline | v2 raw | v2 infra-clean | Delta vs v51 |
| --- | ---: | ---: | ---: | ---: |
| Single-session assistant | 30/30 | 30/30 | 30/30 | 0 |
| Single-session user | 29/30 | 29/30 | 29/30 | 0 |
| Knowledge update | 27/30 | 26/30 | 27/30 | 0 |
| Temporal reasoning | 26/30 | 25/30 | 27/30 | +1 |
| Single-session preference | 29/30 | 26/30 | 26/30 | -3 |
| Multi-session | 21/30 | 19/30 | 19/30 | -2 |
| **Overall** | **162/180** | **155/180** | **158/180** | **-4** |

Against v51 on the same IDs, the clean run had 151 stable passes, 11 stable failures, 7
improvements, and 11 regressions.

## Observability

- Child reports: 333 total, 128 schema-valid (38.44%).
- Episodes with at least one valid child report: 106/180.
- Judge SR with at least one valid child report: 98/106 = 92.45%.
- Judge SR without a valid child report: 60/74 = 81.08%.
- Multi-session had a valid child report in only 10/30 episodes; preference in 13/30.
- Child coverage: 114 complete, 171 incomplete, 48 unspecified.
- Stop reasons: 149 unread memory, 98 assigned scope exhausted, 22 unresolved sources,
  16 two searches with no new source, 48 unspecified.
- Final Compiler coverage: 36 complete, 130 incomplete, 14 uncertain.
- Compiler complete coverage scored 36/36; incomplete coverage scored 108/130.
- Projection status: 54 committed, 112 review, 14 absent. Committed projections scored 51/54.
- The clean artifact has one retained tool error: an Agent-generated unknown ResultLedger ID.

## Failure Analysis

The changes improved temporal reasoning but did not clear the full regression gate.

1. **Child schema and coverage remain the dominant bottleneck.** Multi-session and preference
   rarely produced even one valid child report, and both had zero episodes with final Compiler
   coverage marked complete.
2. **Coverage stopping is descriptive, not yet corrective.** `unread_memory` remained the most
   common stop reason. The parent still compiled incomplete evidence instead of issuing a narrow
   follow-up fork for unresolved sources.
3. **The cardinality Guard can override a correct scalar answer.** In `01493427`, the Compiler
   contract contained the correct answer `25`, but the Guard used four included evidence records
   as the answer and changed the final response to `4 distinct matching actions`.
4. **Aggregation questions are still confused with evidence-item counts.** In `28dc39ac`, the
   requested total play time was replaced by the number of compiled evidence items.
5. **Preference synthesis sometimes returns an evidence summary rather than a recommendation.**
   Four v51 preference passes regressed even though relevant personal evidence was present.

## Decision

Do not promote v2 over v51 yet. Keep the compact Compiler envelope, source-date preservation, and
observability fields, but tighten the next A/B around three general changes:

1. Require a narrow follow-up fork when Compiler coverage is incomplete and unresolved sources remain.
2. Apply cardinality guards only when a committed count contract and its final answer agree with
   the evidence-unit count; never use evidence record count for duration or scalar quantities.
3. Give preference/recommendation contracts a final response shape distinct from an evidence report.

No episode-specific vocabulary should be added.

## Artifacts

- Raw generation: `../work/eval-runs/balanced180-schema-compiler-v2-merged/qa-agent-lab.jsonl`
- Raw judge: `../work/eval-runs/balanced180-schema-compiler-v2-merged/judge-glm52.jsonl`
- Infrastructure-clean generation: `../work/eval-runs/balanced180-schema-compiler-v2-merged/qa-agent-lab-infra-clean.jsonl`
- Infrastructure-clean judge: `../work/eval-runs/balanced180-schema-compiler-v2-merged/judge-glm52-infra-clean.jsonl`
- Infrastructure-clean summary: `../work/eval-runs/balanced180-schema-compiler-v2-merged/judge-glm52-infra-clean.jsonl.summary.json`
