# Catalog Loop v7: Progressive Raw-Memory Reading

## Scope

This iteration keeps the strict runtime contract:

- no `question_type` is passed to the agent;
- no `_abs` suffix inspection;
- one shared parent loop for all question types;
- the parent sees only the question, question date, and a bounded navigation catalog;
- raw memory remains isolated behind child tools;
- no embedding model or reranker.

## Verified score before this change

The final same-condition v6 pilot completed all 18 episodes. Independent `glm-5.2` judging passed 17/18 (94.44%):

| Type | Correct |
| --- | ---: |
| knowledge-update | 3/3 |
| multi-session | 3/3 |
| single-session-assistant | 3/3 |
| single-session-preference | 3/3 |
| single-session-user | 3/3 |
| temporal-reasoning | 2/3 |

The only failure was `gpt4_7abb270c`, which asks for six museum visits in chronological order.

## Root cause

The catalog correctly located the relevant source, but `MemoryRead` returned a complete 15K+ character record into a tool pipeline that bounds each result to 4,000 characters. The child therefore saw a truncated head/tail representation and could not reliably inspect the later turn containing the Museum of Contemporary Art event.

This was an interface mismatch: the tool promised a complete record while the context layer could only expose a bounded result.

## Implementation

`MemoryRead` now exposes raw memory progressively:

```text
MemoryRead(id, offset=0, max_chars<=2400)
  -> content
  -> read_window {
       offset,
       end_offset,
       total_chars,
       has_more,
       next_offset
     }
  -> source + source_refs + temporal metadata
```

Children are instructed to follow `next_offset` when the relevant passage may occur later. Concatenating every returned window reconstructs the original raw content exactly; the store is not summarized or rewritten.

The structured evidence validator also rejects `coverage_status=complete` when `missing_information` admits an unread memory tail.

Separately, the query stream now retries up to two malformed streamed tool inputs. An incomplete JSON tool call is discarded and the next turn is forced to emit one compact valid tool call. Partial arguments never enter conversation history.

## Targeted validation

The museum episode was rerun after the change.

- At the original 2,048 generation-token setting, two runs failed with provider-truncated `ForkSubagent` JSON before evidence reading, and one run stalled before delegation.
- At 4,096 generation tokens, the episode completed in 9 parent turns with `TodoWrite -> 2 ForkSubagent -> CompileEvidence -> final answer`.
- The primary child made 15 `MemoryRead` calls and paged the long source through offsets `0, 2400, 4800, 7200, 9600, 12000`.
- It recovered the Museum of Contemporary Art event and produced the exact six-museum order.
- Independent `glm-5.2` judge: 1/1, yes.

This targeted run validates the access mechanism, but it is not a same-condition replacement for the v6 full score because `max_tokens` changed from 2,048 to 4,096. The official verified full-pilot score remains 17/18 until all 18 episodes are rerun under one fixed v7 configuration.

## Regression tests

`npm test`: 78/78 passing.

The new tests cover lossless paginated reconstruction, source preservation, malformed streamed-tool recovery, and the unread-tail coverage invariant.
