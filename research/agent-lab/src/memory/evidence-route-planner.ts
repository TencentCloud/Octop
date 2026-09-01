import { compileEvidenceBundle, extractQueryFacets } from './evidence-bundle.js'
import type { FileMemoryStore } from './store.js'

export type EvidenceReaderProfile =
  | 'single_fact'
  | 'cross_session_linking'
  | 'aggregate'
  | 'timeline'
  | 'state_resolution'
  | 'assistant_recall'
  | 'preference_profile'
  | 'answerability_audit'

export type EvidenceRiskFlag =
  | 'multi_source'
  | 'temporal_chain'
  | 'state_conflict'
  | 'speaker_sensitive'
  | 'preference_sensitive'
  | 'missing_operand'

export type EvidencePreview = {
  schema_version: '1.0'
  status: 'evidence_found' | 'no_evidence'
  query_facets: string[]
  covered_facets: string[]
  uncovered_facets: string[]
  candidate_memories: number
  source_cluster_count: number
  full_coverage_source_count: number
  complementary_sources: boolean
  role_counts: { user: number; assistant: number; unknown: number }
  date_range: { earliest: string; latest: string } | null
  state_conflict: {
    detected: boolean
    value_kinds: string[]
    competing_value_count: number
    repeated_facets: string[]
  }
  truncated: boolean
}

export type EvidenceRoutePlan = {
  schema_version: '1.0'
  route: 'fork_reader'
  profiles: EvidenceReaderProfile[]
  risk_flags: EvidenceRiskFlag[]
  operations: string[]
  preferred_role: 'user' | 'assistant' | 'any'
  required_facets: string[]
  objective: string
  max_turns: number
  enforce_no_answer_guard: boolean
  preview: EvidencePreview
}

/**
 * Builds a routing contract from observable runtime inputs only. The planner
 * never receives benchmark labels, expected answers, or dataset-specific IDs.
 */
export async function planEvidenceRoute(
  store: FileMemoryStore,
  query: string,
  _referenceDate?: string,
): Promise<EvidenceRoutePlan> {
  const preview = await compileEvidencePreview(store, query)
  const signals = analyzeQuestion(query)
  const evidenceConflictApplies = preview.state_conflict.detected &&
    !signals.preference &&
    !signals.assistantRecall &&
    !/\b(?:why|reason|cause|explain)\b/i.test(query) &&
    /\b(?:what|which|where|how many|how much|current|currently|now|latest|most recent|previous)\b/i.test(query)
  const profiles = new Set<EvidenceReaderProfile>()
  const risks = new Set<EvidenceRiskFlag>()
  const operations = new Set<string>()

  if (signals.assistantRecall) {
    profiles.add('assistant_recall')
    risks.add('speaker_sensitive')
    operations.add('preserve_speaker_attribution')
  }
  if (signals.preference) {
    profiles.add('preference_profile')
    risks.add('preference_sensitive')
    operations.add('extract_preferences_and_constraints')
  }
  if (signals.temporal) {
    profiles.add('timeline')
    risks.add('temporal_chain')
    operations.add('resolve_event_dates')
    operations.add('apply_temporal_boundaries')
  }
  if (signals.aggregate) {
    profiles.add('aggregate')
    risks.add('multi_source')
    operations.add('deduplicate_events')
    operations.add('aggregate_requested_relation')
  }
  if (signals.state || evidenceConflictApplies) {
    profiles.add('state_resolution')
    risks.add('state_conflict')
    operations.add('order_competing_states')
    operations.add('separate_pending_from_completed')
  }

  const needsCrossSourceLinking = signals.aggregate || preview.complementary_sources
  if (needsCrossSourceLinking) {
    profiles.add('cross_session_linking')
    risks.add('multi_source')
    operations.add('link_complementary_sources')
  }

  const materiallyUncovered = preview.uncovered_facets.length > 0 && (
    preview.covered_facets.length === 0 ||
    preview.uncovered_facets.length >= preview.covered_facets.length
  )
  if (signals.answerability || materiallyUncovered || preview.status === 'no_evidence') {
    profiles.add('answerability_audit')
    risks.add('missing_operand')
    operations.add('verify_required_operands')
    operations.add('distinguish_zero_from_missing')
  }

  if (profiles.size === 0) {
    profiles.add('single_fact')
    operations.add('extract_single_supported_fact')
  }

  const profileList = [...profiles]
  return {
    schema_version: '1.0',
    route: 'fork_reader',
    profiles: profileList,
    risk_flags: [...risks],
    operations: [...operations],
    preferred_role: signals.assistantRecall ? 'assistant' : 'user',
    required_facets: preview.query_facets,
    objective: objectiveForProfiles(profileList),
    max_turns: profileList.length === 1 && profileList[0] === 'single_fact' ? 3 : 5,
    enforce_no_answer_guard: profiles.has('answerability_audit'),
    preview,
  }
}

export async function compileEvidencePreview(
  store: FileMemoryStore,
  query: string,
): Promise<EvidencePreview> {
  const bundle = await compileEvidenceBundle(store, query, {
    maxSources: 10,
    maxSnippetsPerSource: 2,
    maxSnippetChars: 240,
    maxChars: 8_000,
    preferredRole: 'any',
  })
  const facets = extractQueryFacets(query)
  const coverageBySource = bundle.source_clusters.map(cluster => new Set(
    cluster.snippets.flatMap(snippet => snippet.matched_facets),
  ))
  const fullCoverageSourceCount = coverageBySource.filter(coverage =>
    facets.length > 0 && facets.every(facet => coverage.has(facet)),
  ).length
  const union = new Set(coverageBySource.flatMap(coverage => [...coverage]))
  const coveredFacets = bundle.covered_facets
  const complementarySources = bundle.source_clusters.length > 1 &&
    fullCoverageSourceCount === 0 &&
    coveredFacets.length >= 2 &&
    coveredFacets.every(facet => union.has(facet)) &&
    !coverageBySource.some(coverage => coveredFacets.every(facet => coverage.has(facet)))
  const roleCounts = { user: 0, assistant: 0, unknown: 0 }
  for (const snippet of bundle.source_clusters.flatMap(cluster => cluster.snippets)) {
    roleCounts[snippet.role]++
  }
  const dates = bundle.source_clusters.map(cluster => cluster.source_date).filter(Boolean).sort()
  const stateConflict = detectStateConflict(bundle.source_clusters, query, facets)

  return {
    schema_version: '1.0',
    status: bundle.status,
    query_facets: facets,
    covered_facets: bundle.covered_facets,
    uncovered_facets: bundle.uncovered_facets,
    candidate_memories: bundle.stats.candidate_memories,
    source_cluster_count: bundle.source_clusters.length,
    full_coverage_source_count: fullCoverageSourceCount,
    complementary_sources: complementarySources,
    role_counts: roleCounts,
    date_range: dates.length > 0 ? { earliest: dates[0]!, latest: dates.at(-1)! } : null,
    state_conflict: stateConflict,
    truncated: bundle.stats.truncated,
  }
}

function detectStateConflict(
  clusters: Array<{ source_ref: string; snippets: Array<{ text: string; matched_facets: string[] }> }>,
  query: string,
  facets: readonly string[],
): EvidencePreview['state_conflict'] {
  const valuesByKind = new Map<string, Map<string, Set<string>>>()
  const facetSources = new Map<string, Set<string>>()
  for (const cluster of clusters) {
    for (const snippet of cluster.snippets) {
      const matchedQueryFacets = snippet.matched_facets.filter(facet => facets.includes(facet))
      for (const facet of snippet.matched_facets) {
        const sources = facetSources.get(facet) ?? new Set<string>()
        sources.add(cluster.source_ref)
        facetSources.set(facet, sources)
      }
      if (matchedQueryFacets.length < Math.min(2, facets.length)) continue
      for (const value of extractStateValues(snippet.text, query)) {
        const kindValues = valuesByKind.get(value.kind) ?? new Map<string, Set<string>>()
        const sources = kindValues.get(value.value) ?? new Set<string>()
        sources.add(cluster.source_ref)
        kindValues.set(value.value, sources)
        valuesByKind.set(value.kind, kindValues)
      }
    }
  }

  const competingKinds = [...valuesByKind.entries()].flatMap(([kind, values]) => {
    const crossSourceValues = [...values.entries()].filter(([, sources]) => sources.size > 0)
    const sourceUnion = new Set(crossSourceValues.flatMap(([, sources]) => [...sources]))
    return crossSourceValues.length > 1 && sourceUnion.size > 1 ? [kind] : []
  })
  const repeatedFacets = facets.filter(facet => (facetSources.get(facet)?.size ?? 0) > 1)
  const competingValueCount = competingKinds.reduce((sum, kind) =>
    sum + (valuesByKind.get(kind)?.size ?? 0), 0)

  return {
    detected: competingKinds.length > 0 && repeatedFacets.length >= Math.min(2, facets.length),
    value_kinds: competingKinds,
    competing_value_count: competingValueCount,
    repeated_facets: repeatedFacets,
  }
}

function extractStateValues(text: string, query: string): Array<{ kind: string; value: string }> {
  const normalized = text.toLowerCase().replace(/\s+/g, ' ')
  const values: Array<{ kind: string; value: string }> = []
  for (const match of normalized.matchAll(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g)) {
    values.push({ kind: 'time', value: match[0] })
  }
  for (const match of normalized.matchAll(/\b\d[\d,]*(?:\.\d+)?\b/g)) {
    const value = match[0].replace(/,/g, '')
    if (/^(?:19|20)\d{2}$/.test(value)) continue
    if (match.index !== undefined && /[:/\-]$/.test(normalized.slice(Math.max(0, match.index - 1), match.index))) continue
    const after = normalized.slice((match.index ?? 0) + match[0].length, (match.index ?? 0) + match[0].length + 1)
    if (/[:/\-]/.test(after)) continue
    values.push({ kind: 'number', value })
  }
  const numberWords: Record<string, string> = {
    zero: '0', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6', seven: '7', eight: '8', nine: '9', ten: '10',
    eleven: '11', twelve: '12', thirteen: '13', fourteen: '14', fifteen: '15', sixteen: '16', seventeen: '17', eighteen: '18', nineteen: '19', twenty: '20',
  }
  for (const match of normalized.matchAll(/\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b/g)) {
    values.push({ kind: 'number', value: numberWords[match[0]]! })
  }
  for (const match of normalized.matchAll(/\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/g)) {
    values.push({ kind: 'weekday', value: match[0] })
  }
  for (const match of normalized.matchAll(/\b(?:daily|weekly|biweekly|monthly|annually|once a week|twice a week|every (?:other )?(?:day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|every \w+ weeks?)\b/g)) {
    values.push({ kind: 'frequency', value: match[0] })
  }
  if (/\bwhere\b|\bkeep\b|\bstor(?:e|ed|ing)\b|\bliv(?:e|ing)\b|\bmov(?:e|ed|ing)\b|\brelocat/.test(query.toLowerCase())) {
    for (const match of normalized.matchAll(/\b(?:keep|kept|store|stored|live|lived|move|moved|relocate|relocated|put)\b.{0,24}?\b(?:to|in|at|under|on|inside)\s+([^,.!?;]{1,40})/g)) {
      values.push({ kind: 'location', value: match[1]!.trim() })
    }
  }
  return deduplicateStateValues(values)
}

function deduplicateStateValues(values: Array<{ kind: string; value: string }>) {
  const seen = new Set<string>()
  return values.filter(value => {
    const key = `${value.kind}:${value.value}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function analyzeQuestion(query: string) {
  const value = query.toLowerCase()
  const hasCalendarMonth = /\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b/.test(value)
  return {
    temporal: hasCalendarMonth || /how (?:many )?(?:days?|weeks?|months?|years?|hours?|long)|how (?:many|much) time|when\b|what (?:date|day|month|year|time)|before|after|between|from (?:first|earliest)|starting from the earliest|happened (?:first|last)|(?:which|who|what) .{0,50} first|order (?:of|from)|in (?:what|which) order|ago\b|since\b|until\b|last (?:week|weekend|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|past (?:week|weekend|month|two months)|timeline/.test(value),
    aggregate: /how many|how much|average|percentage|minimum|maximum|\bmost\b|\bleast\b|total|page count|ratio|\ball\b|\bboth\b|\beach\b|different|altogether/.test(value),
    state: /current|currently|now\b|latest|most recent|recent relocation|still\b|update|changed|switch|previous|formerly|used to|more frequently|less frequently|how often|new (?:job|role|address)/.test(value),
    assistantRecall: /previous (?:chat|conversation)|last time|we (?:talked|discussed)|you (?:suggested|recommended|said|told|gave|provided|mentioned|wrote)|remind me|do you remember|our previous/.test(value),
    preference: /recommend|suggest|tips?\b|resources?\b|advice|ideas? on how|what should i|for me to (?:watch|read|buy|visit)|might find interesting|inspiration|do you think|what do you think|would (?:it|this) be (?:a )?good idea|could there be a reason|might (?:it|this) be/.test(value),
    answerability: /\bexact(?:ly)?\b|\bspecific\b|between|compare|other (?:four|three|two)|all seasons|from whom|what was the name/.test(value),
  }
}

function objectiveForProfiles(profiles: readonly EvidenceReaderProfile[]): string {
  const objectives: Record<EvidenceReaderProfile, string> = {
    single_fact: 'Recover the single directly supported fact and its source without broadening the claim.',
    cross_session_linking: 'Link complementary facts across sessions by shared entities and events before drawing a conclusion.',
    aggregate: 'Build separate entity and event ledgers, deduplicate events, and apply the aggregation requested by the question.',
    timeline: 'Build a sourced timeline with exact event anchors, relative dates, ordering, and inclusive or exclusive boundaries.',
    state_resolution: 'Build an old-to-new state ledger, separate plans from completed facts, and resolve conflicts using explicit support.',
    assistant_recall: 'Recover prior assistant-authored content while preserving speaker attribution.',
    preference_profile: 'Extract user preferences, constraints, and exclusions, then support a personalized answer without inventing preferences.',
    answerability_audit: 'Verify every required entity, relation, time range, and comparison operand; distinguish explicit zero from missing evidence.',
  }
  return profiles.map(profile => objectives[profile]).join(' ')
}
