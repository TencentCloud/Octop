# Catalog Loop v26 Expansion Gate

This document records the final strict no-type-prior expansion gate. Results are added after the merged judge run completes.

## Runtime Contract

- The agent receives history, timestamps, the question, and question date only.
- No `question_type` or `_abs` signal is available at runtime.
- All six question types use the same orchestrator-ledger-catalog loop.
- The parent uses `TodoWrite`, `ForkSubagent`, and `CompileEvidence`.
- Raw memory remains immutable; frontmatter is navigation; event records preserve exact sourced turns.

## v26 Changes

- Retry-safe Query Stream handling for empty responses and unavailable tool hallucinations.
- Source-balanced Event Ledger preloading with explicit user obligations prioritized before ordinary matches.
- Hard child max-turn enforcement and a two-turn compiler cap with deterministic fallback.
- CompileEvidence automatically unions successful Fork result IDs from the parent context.
- Explicit action obligations are reconciled as separate endpoints instead of deduplicated physical entities.
- Compiler `derived_count` is checked against included task units for action-count questions.
- Parent-visible compiler results use a compact structured contract that remains below tool-result truncation limits.
- A final answer guard prevents parent synthesis from overriding the compiled action-count contract.
- Evaluation rows expose compiler count, included-unit count, reconciliation, and answer-guard events.

## Historical Gate

- v7 fixed 18: 14/18.
- v14 fixed 18: 15/18; multi-session remained 1/3 and 11/18 episodes had at least one invalid child report.
- Targeted fixes independently passed `6d550036` and `75832dbd` before the final action-ledger work.

## v26 Result

- Independent `glm-5.2` judge: 16/18 = 88.89%.
- Type accuracy: preference 3/3, multi-session 2/3, single-session-user 2/3, knowledge-update 3/3, temporal 3/3, assistant recall 3/3.
- Failures: `51a45a95` was too conservative about a same-session Target discourse bridge; `gpt4_59c863d7` found but did not preserve the Tiger I search hit.

## v27-v29 Targeted Work

- Added same-session discourse bridging for one uniquely active surrounding entity.
- Limited repeated `MemorySearch` calls and required search-to-read progress.
- Made MemorySearch return compact parseable hits with a `summary_complete` marker.
- Preserved complete Event Ledger hits from child tool results as `discovered_evidence` in ResultLedger.
- Both prior failures passed independent targeted judge, 2/2.

## v30 Final Gate

- Structural: 18/18 completed, 0 empty answers, 0 tool-error episodes.
- Average parent turns: 3.83.
- Average general-child turns per episode: 14.39, improved from 15.39 in v26.
- Episodes with at least one invalid child report: 9/18, improved from 10/18 in v26.
- Episodes preserving discovered search evidence: 16/18.
- Independent `glm-5.2` judge: 15/18 = 83.33%.
- Type accuracy: preference 3/3, multi-session 1/3, single-session-user 2/3, knowledge-update 3/3, temporal 3/3, assistant recall 3/3.
- Failures: `51a45a95`, `6d550036`, and `gpt4_59c863d7`.

## Decision

Do not expand to 180 episodes yet. Targeted success did not remain stable in the fixed 18-episode rerun. The next gate should focus on deterministic compiler invariants for predicate fidelity and on source-complete discovery coverage, then require at least 17/18 on two repeated fixed-set runs before scaling.

## v31-v45 Compiler And Ledger Work

- ResultLedger now preserves exact, task-relevant user evidence read by child tools even when a child final report is malformed or reaches its turn limit.
- MemorySearch uses a larger candidate pool followed by source-balanced selection; the parent still receives only result IDs and compact summaries.
- CompileEvidence gained sourced count contracts, same-session discourse resolution, latest-state resolution, and explicit leadership/action audits.
- Compiler responses truncated after a complete `included` array can be recovered only when the declared count matches the complete census and every item has at least one known source.
- v42 fixed 18 scored 16/18. Targeted v44 then passed both the model-kit count and Premiere preference cases, 2/2.
- v45 fixed 18 again scored 16/18. The failures were the model-kit count and Rachel latest-state update, demonstrating that targeted success was not yet stable.

## v46-v48 Root Cause Fixes

- Added a source-backed StateTransitionAudit. It selects the latest explicit user move/relocation endpoint by source date, so Rachel resolves to `the suburbs` rather than the older Chicago state.
- Removed the unsafe behavior that created counted units directly from raw discovered search hits. This behavior had incorrectly treated a Walmart chicken purchase as model-kit evidence.
- Added a conditional schema-repair compiler sidechain for malformed compiler JSON. Repair remains a fallback, not the primary path.
- The main truncation cause was the 2048 completion-token budget: `reasoning_content` consumed most of that budget and left child/compiler JSON incomplete. Raising the evaluation default to 4096 produced complete structured reports and a complete compiler packet.
- Count-unit deduplication was made conservative (`0.85` claim similarity with shared provenance), preventing a B-29 and Camaro bought in the same source turn from being merged.
- Targeted v48 returned all five model kits and passed the independent judge. Replaying its compiler packet with the final deduplication logic produced a consistent `5/5` deterministic contract.

## v49 Fixed Gate

- Structural: 18/18 completed, 0 empty answers, 1 episode with a recovered tool timeout.
- Average parent turns: 3.94; average forks: 1.78.
- Episodes with at least one invalid child report: 12/18, down from 16/18 in v45.
- Valid structured child reports: 15/32. Conditional compiler repair ran in 2 episodes.
- Independent `glm-5.2` judge: 17/18 = 94.44%.
- Type accuracy: preference 3/3, multi-session 3/3, single-session-user 3/3, knowledge-update 2/3, temporal 3/3, assistant recall 3/3.
- The sole failure was a newer explicit aggregate count (`four Korean restaurants`) being excluded because individual restaurant names were unavailable.

## v50 Aggregate Count Semantics

- The compiler contract now treats a dated explicit user aggregate count as sufficient when the question asks only for the total.
- A newer matching aggregate state supersedes an older itemized snapshot; missing member names are uncertainty metadata, not grounds for excluding the aggregate.
- Targeted `6aeb4375` returned four and passed the independent judge.

## Current Decision

The first 17/18 fixed-set gate has passed, and all three multi-session episodes passed under the same no-prior loop. Do not scale to 180 yet. Run one more unchanged fixed-18 repetition; expand only if it also scores at least 17/18. The next optimization target is child-report validity and cost, not additional episode-specific retrieval vocabulary.

## v51 Balanced 180

The balanced expansion was subsequently run at 30 episodes per type. Generation completed 180/180 after resume-only retries, and the independent judge scored 162/180 (90.0%). Multi-session fell to 21/30 (70.0%), while the other five types ranged from 86.67% to 100%. See `docs/balanced-180-v51-results.md` for the full breakdown. This larger run supersedes the fixed-set gate as the current optimization baseline.
