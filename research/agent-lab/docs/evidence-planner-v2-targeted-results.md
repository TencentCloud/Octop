# Evidence Planner V2 Targeted Results

## Scope

This is a targeted repair gate, not an unbiased benchmark score. The four final
episodes were selected because all four failed the previous 180-episode
majority evaluation and directly exercise the V2 changes.

Runtime conditions remained blind: the Agent received conversation history,
timestamps, question, and question date. It did not receive `question_type`, an
`_abs` signal, a reference answer, or gold tags.

## Changes Under Test

- Preference-specific answer synthesis, including implicit advice wording.
- Evidence-preview state conflict detection using source-separated values.
- Two-stage Reader reporting with a bounded, tool-free report compiler.
- Deterministic report compaction, query-kind normalization, and partial JSON
  recovery.
- Source dates in compiler evidence packets.
- Lexical facet cleanup and explicit aliases for phone charging evidence.

## Final Targeted Gate

| Episode | Type | Previous majority | V2 judge |
|---|---|---:|---:|
| `09d032c9` | preference | fail | pass |
| `1d4e3b97` | preference | fail | pass |
| `f9e8c073` | knowledge-update | fail | pass |
| `e66b632c` | knowledge-update | fail | pass |
| **Total** | | **0 / 4** | **4 / 4** |

All four final Reader reports were valid. The preference answers used the
recovered personal evidence: power bank and wireless charging pad for the phone
question, and chain/cassette replacement plus Garmin bike computer for the bike
question. The state answers selected five support-group sessions as the later
recollection and distinguished the previous 5K best of 27:45 from the newer
26:30 result.

An earlier compiler smoke also recovered valid Stage 2 reports for two
multi-session episodes whose Stage 1 Readers ended with no report after hitting
the turn limit. This verifies that the compiler can operate from its bounded
evidence packet without inheriting the Reader conversation.

## Artifacts

- `work/eval-runs/agent-lab-planner-v5-targeted4-final/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-planner-v5-targeted4-final/qa-judge-glm52.jsonl`
- `work/eval-runs/agent-lab-planner-v5-targeted4-final/qa-judge-glm52.jsonl.summary.json`
- `work/eval-runs/agent-lab-planner-v3-smoke8-shard0/qa-agent-lab.jsonl`
- `work/eval-runs/agent-lab-planner-v3-smoke8-shard1/qa-agent-lab.jsonl`

## Interpretation

The targeted failures are fixed, but this result must not be reported as a new
overall SR. The next valid generalization gate is a fresh balanced subset or a
full rerun with the same blind protocol. Preview conflict precision and staged
compiler invocation rates should be reported alongside judge accuracy.
