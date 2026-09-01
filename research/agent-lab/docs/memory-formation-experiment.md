# Memory Formation Experiment

## Principle

Raw Memory remains lossless, Frontmatter is navigation-only, Event Ledger organizes sourced atomic candidates, and Evidence Result serves only the current question. Every persistent derived record retains references to raw memory and source turns.

## Implementation

- Raw conversation sessions are stored as immutable `evidence` records.
- Episode Frontmatter is stored as compact `topic` records derived from raw sessions.
- Each source turn is stored conservatively as an `event` candidate with `event_status=uncertain`; semantic merging is not performed at write time yet.
- The parent receives one bounded Memory Catalog snapshot and cannot read raw memory directly.
- Two read-only ForkSubagent tasks may run concurrently: assigned-source coverage and omitted-source/identity/time audit.
- ResultLedger parses structured Evidence Results and recovers complete sourced candidates from truncated JSON.
- CompileEvidence receives recovered structured evidence without duplicating full raw child output.

## Verification

- Local tests: 68/68 passing.
- Same 20 multi-session episodes as Experiment B, offline formation/catalog diagnostic:
  - Initial catalog mean answer-source recall: 74.75%.
  - Compacted catalog mean answer-source recall: 89.17%.
  - Perfect answer-source coverage: 15/20.
  - Mean selected sources: 10.55.
  - Mean formed turn-event candidates: 485.9 per episode.

The `answer_` source prefix is used only by the offline diagnostic to measure recall. It is never written into runtime tags or supplied to the agent as a relevance label.

## Historical Failure Check

| Episode | Previous result | Formation result | Attribution |
| --- | --- | --- | --- |
| `gpt4_a56e767c` | 3/4 festivals | 4/4 | Turn-level event navigation recovered Seattle from within a long session. |
| `gpt4_7fce9456` | 3/4 properties | 4/4 | Compact catalog covered all five sequence sources; structured output and compiler completed. |
| `gpt4_2f8be40d` | Overcounted 5 weddings | Incorrect 2 | Catalog covered only 1/3 answer sources; semantic source formation remains insufficient. |
| `88432d0a` | Overcounted 5-6 baking events | Incorrect 0 | Catalog covered only 1/4 answer sources; lexical navigation did not normalize `made` events to baking. |
| `7024f17c` | 0 hours | 0 hours | Evidence was recovered, but calendar-week interpretation excludes May 20 while benchmark gold includes it. |

## Conclusion

The formation layers improve intra-session event recall and source-sequence coverage, fixing two retrieval failures without question-type prior or domain vocabulary rules. They do not yet solve semantic event formation: a conservative turn index cannot normalize actions, identify event coreference, or establish persona coherence by itself.

Do not run the full 20-episode model A/B yet. The next gate is a general, sourced MemoryFormer that extracts compact action/entity/time facets at write time, followed by the same offline catalog diagnostic. Full model evaluation becomes reasonable after answer-source recall exceeds 95% without runtime gold labels.
