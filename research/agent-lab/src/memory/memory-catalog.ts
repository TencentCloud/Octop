import { extractQueryFacets } from './evidence-bundle.js'
import type { FileMemoryStore } from './store.js'
import type { MemoryHit, MemoryRecord } from './types.js'

export type MemoryCatalogEventPreview = {
  memory_id: string
  turn_ref?: string
  speaker: string
  summary: string
}

export type MemoryCatalogCard = {
  source_ref: string
  source_date: string
  frontmatter_id?: string
  raw_memory_id?: string
  event_count_hint: number
  summary: string
  matched_events: MemoryCatalogEventPreview[]
}

export type MemoryCatalog = {
  schema_version: '1.0'
  purpose: 'navigation_only'
  query: string
  cards: MemoryCatalogCard[]
  stats: {
    candidate_records: number
    selected_sources: number
    chars: number
    truncated: boolean
  }
}

export async function searchMemoryCatalog(
  store: FileMemoryStore,
  query: string,
  options: { maxSources?: number; maxEventsPerSource?: number; maxChars?: number } = {},
): Promise<MemoryCatalog> {
  const maxSources = boundedInteger(options.maxSources, 12, 1, 30)
  const maxEventsPerSource = boundedInteger(options.maxEventsPerSource, 3, 1, 12)
  const maxChars = boundedInteger(options.maxChars, 8_000, 1_000, 30_000)
  const facets = extractQueryFacets(query)
  const variants = [query, ...facets].filter((value, index, all) => value && all.indexOf(value) === index)
  const searches = await Promise.all(variants.flatMap(variant => [
    store.search({ query: variant, kinds: ['topic'], limit: 50 }),
    store.search({ query: variant, kinds: ['event'], limit: 50 }),
  ]))
  const ranked = mergeHits(searches)
  const records = (await Promise.all(ranked.slice(0, 120).map(async candidate => ({
    ...candidate,
    record: await store.read(candidate.hit.id),
  })))).filter((item): item is RankedRecord => item.record !== null)
  const grouped = groupRecords(records, maxEventsPerSource).slice(0, maxSources)
  const bounded = boundCards(grouped, maxChars)
  const base = {
    schema_version: '1.0' as const,
    purpose: 'navigation_only' as const,
    query,
    cards: bounded.cards,
  }
  return {
    ...base,
    stats: {
      candidate_records: ranked.length,
      selected_sources: bounded.cards.length,
      chars: JSON.stringify(base).length,
      truncated: bounded.truncated,
    },
  }
}

type RankedHit = { hit: MemoryHit; score: number }
type RankedRecord = RankedHit & { record: MemoryRecord }

function mergeHits(searches: readonly MemoryHit[][]): RankedHit[] {
  const merged = new Map<string, RankedHit>()
  for (const hits of searches) {
    hits.forEach((hit, rank) => {
      const current = merged.get(hit.id) ?? { hit, score: 0 }
      current.score += hit.score + 1 / (rank + 2)
      merged.set(hit.id, current)
    })
  }
  return [...merged.values()].sort((left, right) =>
    right.score - left.score || right.hit.event_time?.localeCompare(left.hit.event_time ?? '') || 0,
  )
}

function groupRecords(records: readonly RankedRecord[], maxEvents: number): MemoryCatalogCard[] {
  const groups = new Map<string, { card: MemoryCatalogCard; score: number }>()
  for (const candidate of records) {
    const { record } = candidate
    const group = groups.get(record.source.ref) ?? {
      card: {
        source_ref: record.source.ref,
        source_date: record.temporal?.event_time ?? record.source.observed_at,
        event_count_hint: 0,
        summary: '',
        matched_events: [],
      },
      score: 0,
    }
    group.score = Math.max(group.score, candidate.score)
    if (record.tags.includes('memory-layer:frontmatter')) {
      group.card.frontmatter_id = record.id
      group.card.summary = compactText(record.summary, 140)
      const metadata = parseFrontmatter(record.content)
      group.card.raw_memory_id = metadata?.raw_memory_id
      group.card.event_count_hint = metadata?.event_count_hint ?? group.card.event_count_hint
    }
    if (record.tags.includes('memory-layer:event')) {
      group.card.matched_events.push({
        memory_id: record.id,
        ...turnRefFromRecord(record),
        speaker: speakerFromTags(record.tags),
        summary: compactText(record.summary, 180),
      })
      group.card.matched_events = group.card.matched_events.slice(0, maxEvents)
    }
    groups.set(record.source.ref, group)
  }
  return [...groups.values()]
    .sort((left, right) => right.score - left.score || right.card.source_date.localeCompare(left.card.source_date))
    .map(group => group.card)
}

function boundCards(cards: readonly MemoryCatalogCard[], maxChars: number) {
  const selected: MemoryCatalogCard[] = []
  let truncated = false
  for (const card of cards) {
    if (JSON.stringify([...selected, card]).length > maxChars) {
      truncated = true
      continue
    }
    selected.push(card)
  }
  return { cards: selected, truncated }
}

function parseFrontmatter(content: string): { raw_memory_id?: string; event_count_hint?: number } | null {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    return {
      raw_memory_id: typeof parsed.raw_memory_id === 'string' ? parsed.raw_memory_id : undefined,
      event_count_hint: typeof parsed.event_count_hint === 'number' ? parsed.event_count_hint : undefined,
    }
  } catch {
    return null
  }
}

function speakerFromTags(tags: readonly string[]): string {
  return tags.find(tag => tag.startsWith('speaker:'))?.slice('speaker:'.length) ?? 'unknown'
}

function turnRefFromRecord(record: MemoryRecord): { turn_ref?: string } {
  const turnRef = record.source_refs.find(ref => ref.includes('#turn-'))
  return turnRef ? { turn_ref: turnRef } : {}
}

function boundedInteger(value: number | undefined, fallback: number, min: number, max: number): number {
  return Number.isInteger(value) && value! >= min && value! <= max ? value! : fallback
}

function compactText(value: string, maxChars: number): string {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length <= maxChars) return compact
  return `${compact.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`
}
