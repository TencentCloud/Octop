# Error Handling

## Insufficient Search Results
1. Broaden query terms.
2. Search adjacent concepts.
3. Document the gap.
4. Lower confidence appropriately.

## Unresolved Contradictions
1. Present both claims.
2. Analyze methodological differences.
3. Assess evidence quality.
4. Document unresolved status if needed.

## Source Quality Concerns
- Prefer primary sources.
- Flag outdated or biased sources.
- Note unclear methodology.

## Technical Failures
- If `web_fetch` fails, document the URL and proceed.
- On rate limits, slow down and retry with smaller counts.
- If memory search fails, proceed and note limitation.
