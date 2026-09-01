# Schema, Coverage, and Compiler Projection Optimization

## Goal

Improve the generic no-prior memory-agent loop without adding episode-specific retrieval vocabulary.

## Changes

- Added compact child evidence schema `1.1` while retaining `1.0` compatibility.
- Replaced redundant child coverage arrays with an explicit coverage decision:
  inspected sources, unresolved sources, and a bounded stop reason.
- Reconciled child coverage claims against observed `MemorySearch`, `MemoryRead`,
  `MemoryEvidenceBundle`, pagination, and max-turn behavior.
- Added cross-result source coverage reconciliation before Compiler output reaches the parent.
- Added a question-conditioned Compiler `answer_contract` with evidence-ID validation.
- Added a general `duration` operation so elapsed time is not validated as cardinality.
- Bounded the complete Compiler tool envelope to 1,800 characters and placed the evidence
  packet first, leaving room for the surrounding catalog and message history during compression.
- Extended evaluation observability with stop reason, cross-source coverage, and projection status.

## Verification

- TypeScript build: passed.
- Unit and integration tests: 105/105 passed.
- Initial fresh-offset smoke: 5/5 available episodes completed with no runtime errors.
- Targeted final smoke:
  - `b3c15d39` multi-session: `duration`, committed projection, cross-source coverage incomplete but answer evidence sufficient.
  - `gpt4_d6585ce8` temporal: Compiler envelope parseable, projection held for review because a conflict remained.
- Independent GLM-5.2 judge: 2/2 passed.

## Artifacts

- Initial smoke: `../work/eval-runs/schema-coverage-compiler-smoke6/qa-agent-lab.jsonl`
- Final targeted smoke: `../work/eval-runs/schema-coverage-compiler-smoke2-v3/qa-agent-lab.jsonl`
- Final targeted judge: `../work/eval-runs/schema-coverage-compiler-smoke2-v3/judge-glm52.jsonl`

## Interpretation

The targeted run verifies lifecycle behavior, not a statistically meaningful SR increase.
The next gate should be a fixed, fresh temporal plus multi-session A/B that compares the
balanced-180 implementation against this branch using the same IDs, model, budgets, and judge.
Track SR together with child schema validity, Compiler packet parseability, projection commit
rate, coverage stop reasons, and child turns.
