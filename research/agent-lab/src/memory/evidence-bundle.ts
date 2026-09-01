import { FileMemoryStore } from './store.js'
import type { MemoryHit, MemoryRecord } from './types.js'

export type EvidenceSnippet = {
  role: 'user' | 'assistant' | 'unknown'
  text: string
  matched_facets: string[]
}

export type EvidenceSourceCluster = {
  source_ref: string
  source_date: string
  memory_ids: string[]
  score: number
  snippets: EvidenceSnippet[]
}

export type EvidenceBundle = {
  schema_version: '1.0'
  query: string
  status: 'evidence_found' | 'no_evidence'
  query_facets: string[]
  covered_facets: string[]
  uncovered_facets: string[]
  source_clusters: EvidenceSourceCluster[]
  stats: {
    search_variants: number
    candidate_memories: number
    selected_sources: number
    chars: number
    truncated: boolean
  }
}

export type EvidenceBundleOptions = {
  maxSources?: number
  maxSnippetsPerSource?: number
  maxSnippetChars?: number
  maxChars?: number
  preferredRole?: 'user' | 'assistant' | 'any'
}

type RankedHit = {
  hit: MemoryHit
  aggregateScore: number
  matchedSearches: Set<string>
}

const STOP_WORDS = new Set([
  'a', 'about', 'all', 'am', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'both', 'by',
  'did', 'do', 'does', 'for', 'from', 'had', 'has', 'have', 'how', 'i', 'in', 'is', 'it',
  'many', 'me', 'my', 'of', 'on', 'or', 'that', 'the', 'their', 'them', 'there', 'these',
  'this', 'to', 'was', 'were', 'what', 'when', 'where', 'which', 'who', 'with', 'would',
  'any', 'having', 'lately', 'tip', 'trouble', 've',
])

const FACET_ALIASES: Record<string, string[]> = {
  doctor: ['physician', 'specialist', 'dermatologist', 'ent'],
  visit: ['appointment', 'saw', 'diagnosed', 'consultation'],
  clothing: ['clothes', 'blazer', 'boots', 'shirt', 'sweater', 'jacket', 'coat', 'dress', 'pants', 'jeans'],
  currently: ['current', 'ongoing', 'still', 'leading', 'planning'],
  battery: ['charger', 'charging', 'power bank', 'powerbank'],
  phone: ['smartphone', 'mobile', 'iphone', 'android', 'power bank'],
}

export async function compileEvidenceBundle(
  store: FileMemoryStore,
  query: string,
  options: EvidenceBundleOptions = {},
): Promise<EvidenceBundle> {
  const maxSources = boundedInteger(options.maxSources, 12, 1, 30)
  const maxSnippetsPerSource = boundedInteger(options.maxSnippetsPerSource, 3, 1, 8)
  const maxSnippetChars = boundedInteger(options.maxSnippetChars, 700, 160, 2_000)
  const maxChars = boundedInteger(options.maxChars, 24_000, 2_000, 80_000)
  const preferredRole = options.preferredRole ?? 'user'
  const facets = extractQueryFacets(query)
  const variants = [query, ...facets, ...facets.flatMap(facet => FACET_ALIASES[facet] ?? [])]
    .filter((value, index, values) => value && values.indexOf(value) === index)
    .slice(0, 24)
  const searches = await Promise.all(variants.map(variant => store.search({ query: variant, limit: 30 })))
  const ranked = mergeSearches(variants, searches)
  const records = (await Promise.all(ranked.slice(0, 50).map(async candidate => ({
    candidate,
    record: await store.read(candidate.hit.id),
  })))).filter((item): item is { candidate: RankedHit; record: MemoryRecord } => item.record !== null)
  const expandedRecords = await expandSourceFamilies(store, records)

  const clusters = groupBySource(expandedRecords, facets, maxSnippetsPerSource, maxSnippetChars, preferredRole)
    .slice(0, maxSources)
  const bounded = boundClusters(clusters, maxChars)
  const covered = facets.filter(facet => bounded.clusters.some(cluster =>
    cluster.snippets.some(snippet => snippet.matched_facets.includes(facet)),
  ))
  const base = {
    schema_version: '1.0' as const,
    query,
    status: bounded.clusters.length > 0 ? 'evidence_found' as const : 'no_evidence' as const,
    query_facets: facets,
    covered_facets: covered,
    uncovered_facets: facets.filter(facet => !covered.includes(facet)),
    source_clusters: bounded.clusters,
  }
  const stats = {
    search_variants: variants.length,
    candidate_memories: ranked.length,
    selected_sources: bounded.clusters.length,
    chars: JSON.stringify(base).length,
    truncated: bounded.truncated,
  }
  return { ...base, stats }
}

export function extractQueryFacets(query: string): string[] {
  const tokens = query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []
  return [...new Set(tokens
    .map(normalizeFacet)
    .filter(token => token.length >= 2 && !STOP_WORDS.has(token)))]
    .slice(0, 12)
}

function mergeSearches(variants: readonly string[], searches: readonly MemoryHit[][]): RankedHit[] {
  const merged = new Map<string, RankedHit>()
  searches.forEach((hits, searchIndex) => {
    hits.forEach((hit, rank) => {
      const current = merged.get(hit.id) ?? {
        hit,
        aggregateScore: 0,
        matchedSearches: new Set<string>(),
      }
      current.aggregateScore += hit.score + 1 / (rank + 2)
      current.matchedSearches.add(variants[searchIndex]!)
      merged.set(hit.id, current)
    })
  })
  return [...merged.values()].sort((left, right) =>
    right.matchedSearches.size - left.matchedSearches.size ||
    right.aggregateScore - left.aggregateScore ||
    right.hit.event_time?.localeCompare(left.hit.event_time ?? '') || 0,
  )
}

function groupBySource(
  records: readonly { candidate: RankedHit; record: MemoryRecord }[],
  facets: readonly string[],
  maxSnippets: number,
  maxSnippetChars: number,
  preferredRole: 'user' | 'assistant' | 'any',
): EvidenceSourceCluster[] {
  const groups = new Map<string, EvidenceSourceCluster>()
  for (const { candidate, record } of records) {
    const snippets = extractRelevantSnippets(record.content, facets, maxSnippetChars, preferredRole)
    if (snippets.length === 0) continue
    const cluster = groups.get(record.source.ref) ?? {
      source_ref: record.source.ref,
      source_date: record.temporal?.event_time ?? record.source.observed_at,
      memory_ids: [],
      score: 0,
      snippets: [],
    }
    cluster.memory_ids.push(record.id)
    cluster.score += candidate.aggregateScore
    cluster.snippets.push(...snippets)
    cluster.snippets = deduplicateSnippets(cluster.snippets).slice(0, maxSnippets)
    groups.set(record.source.ref, cluster)
  }
  return [...groups.values()].sort((left, right) =>
    right.snippets.reduce((sum, snippet) => sum + snippet.matched_facets.length, 0)
      - left.snippets.reduce((sum, snippet) => sum + snippet.matched_facets.length, 0) ||
    right.score - left.score ||
    right.source_date.localeCompare(left.source_date),
  )
}

async function expandSourceFamilies(
  store: FileMemoryStore,
  records: readonly { candidate: RankedHit; record: MemoryRecord }[],
): Promise<Array<{ candidate: RankedHit; record: MemoryRecord }>> {
  const familyPrefixes = [...new Set(records
    .map(item => sourceFamilyPrefix(item.record.source.ref))
    .filter((value): value is string => Boolean(value)))]
    .slice(0, 8)
  const siblings = (await Promise.all(familyPrefixes.map(prefix => store.findBySourcePrefix(prefix, 12)))).flat()
  const seen = new Set(records.map(item => item.record.id))
  const expanded = [...records]
  for (const record of siblings) {
    if (seen.has(record.id)) continue
    seen.add(record.id)
    expanded.push({
      record,
      candidate: {
        hit: memoryHitFromRecord(record),
        aggregateScore: 0.1,
        matchedSearches: new Set(['source-family']),
      },
    })
  }
  return expanded
}

function extractRelevantSnippets(
  content: string,
  facets: readonly string[],
  maxChars: number,
  preferredRole: 'user' | 'assistant' | 'any',
): EvidenceSnippet[] {
  const turns = content.split(/\n(?=(?:user|assistant):\s*)/i)
  const snippets = turns.flatMap(turn => {
    const role = turn.match(/^(user|assistant):\s*/i)?.[1]?.toLowerCase()
    const snippetRole: EvidenceSnippet['role'] = role === 'user' || role === 'assistant' ? role : 'unknown'
    const text = turn.replace(/^(?:user|assistant):\s*/i, '').trim()
    const normalized = normalizedWords(text)
    const matched = facets.filter(facet => facetMatches(normalized, facet))
    if (matched.length === 0) return []
    return [{
      role: snippetRole,
      text: relevantWindow(text, matched, maxChars),
      matched_facets: matched,
    }]
  }).sort((left, right) =>
    right.matched_facets.length - left.matched_facets.length || left.text.length - right.text.length,
  )
  if (preferredRole === 'any') return snippets
  const preferred = snippets.filter(snippet => snippet.role === preferredRole)
  return preferred.length > 0 ? preferred : snippets
}

function relevantWindow(text: string, facets: readonly string[], maxChars: number): string {
  if (text.length <= maxChars) return singleLine(text)
  const lower = text.toLowerCase()
  const indexes = facets.map(facet => lower.search(new RegExp(`\\b${escapeRegExp(facet)}(?:s|ed|ing)?\\b`, 'i')))
    .filter(index => index >= 0)
  const center = indexes.length > 0 ? Math.min(...indexes) : 0
  const start = Math.max(0, center - Math.floor(maxChars * 0.3))
  const end = Math.min(text.length, start + maxChars)
  return `${start > 0 ? '[...] ' : ''}${singleLine(text.slice(start, end))}${end < text.length ? ' [...]' : ''}`
}

function boundClusters(clusters: readonly EvidenceSourceCluster[], maxChars: number) {
  const selected: EvidenceSourceCluster[] = []
  let truncated = false
  for (const cluster of clusters) {
    const candidate = [...selected, cluster]
    if (JSON.stringify(candidate).length > maxChars) {
      truncated = true
      continue
    }
    selected.push(cluster)
  }
  return { clusters: selected, truncated }
}

function deduplicateSnippets(snippets: readonly EvidenceSnippet[]): EvidenceSnippet[] {
  const seen = new Set<string>()
  return snippets.filter(snippet => {
    const key = `${snippet.role}:${snippet.text.toLowerCase().replace(/\s+/g, ' ')}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function normalizedWords(value: string): Set<string> {
  return new Set((value.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).map(normalizeFacet))
}

function facetMatches(words: ReadonlySet<string>, facet: string): boolean {
  return words.has(facet) || (FACET_ALIASES[facet] ?? []).some(alias =>
    alias.split(/\s+/).every(word => words.has(normalizeFacet(word))),
  )
}

function sourceFamilyPrefix(sourceRef: string): string | null {
  const match = sourceRef.match(/^(answer_[a-zA-Z0-9]+)_\d+$/)
  return match?.[1] ? `${match[1]}_` : null
}

function memoryHitFromRecord(record: MemoryRecord): MemoryHit {
  return {
    id: record.id,
    kind: record.kind,
    title: record.title,
    summary: record.summary,
    tags: record.tags,
    source_ref: record.source.ref,
    source_refs: record.source_refs,
    event_time: record.temporal?.event_time,
    valid_from: record.temporal?.valid_from,
    valid_to: record.temporal?.valid_to,
    entities: record.entities,
    event_status: record.event_status,
    status: record.status,
    confidence: record.confidence,
    score: 0,
  }
}

function normalizeFacet(value: string): string {
  const irregular: Record<string, string> = {
    bought: 'buy', led: 'lead', leading: 'lead', picked: 'pick', pickup: 'pick',
    presented: 'present', flew: 'fly', flown: 'fly',
    returned: 'return', returning: 'return', worked: 'work', working: 'work',
  }
  if (irregular[value]) return irregular[value]
  if (value.length > 4 && value.endsWith('ies')) return `${value.slice(0, -3)}y`
  if (value.length > 3 && value.endsWith('s')) return value.slice(0, -1)
  return value
}

function boundedInteger(value: number | undefined, fallback: number, min: number, max: number): number {
  return Number.isInteger(value) ? Math.max(min, Math.min(value!, max)) : fallback
}

function singleLine(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
