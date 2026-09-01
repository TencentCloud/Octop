import { buildTool, type Tool } from '../core/tool.js'
import { compileEvidenceBundle } from './evidence-bundle.js'
import { FileMemoryStore } from './store.js'
import { searchMemoryCatalog } from './memory-catalog.js'
import type {
  EventStatus,
  MemoryHit,
  MemoryKind,
  MemoryRelation,
  MemorySource,
  MemoryTemporal,
} from './types.js'

type SearchInput = {
  query: string
  kinds?: MemoryKind[]
  limit?: number
}

type ReadInput = {
  id: string
  offset?: number
  max_chars?: number
}

const DEFAULT_MEMORY_READ_CHARS = 1_800
const MAX_MEMORY_READ_CHARS = 2_400

type EvidenceBundleInput = {
  query: string
  max_sources?: number
  max_chars?: number
  preferred_role?: 'user' | 'assistant' | 'any'
}

type CatalogSearchInput = {
  query: string
  max_sources?: number
  max_events_per_source?: number
  max_chars?: number
}

type CreateInput = {
  kind: MemoryKind
  title: string
  summary: string
  content: string
  tags?: string[]
  source: MemorySource
  temporal?: MemoryTemporal
  confidence?: number
  source_refs?: string[]
  entities?: string[]
  event_status?: EventStatus
  supersedes?: string[]
  relations?: MemoryRelation[]
}

type UpdateInput = {
  id: string
  title?: string
  summary?: string
  content?: string
  tags?: string[]
  temporal?: MemoryTemporal
  confidence?: number
  status?: 'active' | 'superseded'
  source_refs?: string[]
  entities?: string[]
  event_status?: EventStatus
  supersedes?: string[]
  relations?: MemoryRelation[]
  expected_revision?: number
  source_ref: string
}

type DeleteInput = { id: string; source_ref: string }

export function createMemoryTools(store: FileMemoryStore): Tool[] {
  const catalogSearch = buildTool<CatalogSearchInput, unknown>({
    name: 'MemoryCatalogSearch',
    description: 'Search compact Episode Frontmatter and Event Ledger previews for planning. Navigation only: delegate raw-memory verification before answering.',
    inputSchema: {
      query: { type: 'string', required: true },
      max_sources: { type: 'number' },
      max_events_per_source: { type: 'number' },
      max_chars: { type: 'number' },
    },
    maxResultSizeChars: 30_000,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    validateInput: async input => {
      if (!input.query.trim()) return { result: false, message: 'query must not be empty' }
      if (input.max_sources !== undefined && (!Number.isInteger(input.max_sources) || input.max_sources < 1 || input.max_sources > 30)) {
        return { result: false, message: 'max_sources must be an integer between 1 and 30' }
      }
      if (input.max_events_per_source !== undefined && (!Number.isInteger(input.max_events_per_source) || input.max_events_per_source < 1 || input.max_events_per_source > 12)) {
        return { result: false, message: 'max_events_per_source must be an integer between 1 and 12' }
      }
      return { result: true }
    },
    call: input => searchMemoryCatalog(store, input.query, {
      maxSources: input.max_sources,
      maxEventsPerSource: input.max_events_per_source,
      maxChars: input.max_chars,
    }),
  })

  const search = buildTool<SearchInput, unknown>({
    name: 'MemorySearch',
    description: 'Search memory summaries. Read a hit by id before relying on its full evidence.',
    inputSchema: {
      query: { type: 'string', required: true },
      limit: { type: 'number' },
      kinds: { type: 'array', items: { type: 'string' } },
    },
    maxResultSizeChars: 8_000,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    validateInput: async input => validateKinds(input.kinds),
    call: async input => {
      const resultLimit = Math.min(input.limit ?? 8, 8)
      const candidates = await store.search({ ...input, limit: Math.max(resultLimit * 3, 24) })
      const hits = selectSourceBalancedHits(candidates, resultLimit)
      return hits.map(hit => ({
        id: hit.id,
        kind: hit.kind,
        summary: hit.summary.slice(0, 350),
        summary_complete: hit.summary_complete === true && hit.summary.length <= 350,
        speaker: hit.tags.find(tag => tag === 'user' || tag === 'assistant'),
        source_ref: hit.source_ref,
        source_refs: hit.source_refs.slice(0, 2),
        event_time: hit.event_time,
        score: hit.score,
      }))
    },
  })

  const read = buildTool<ReadInput, unknown>({
    name: 'MemoryRead',
    description: 'Read one bounded window of a raw memory record with provenance. max_chars must be 256-2400. Start at offset 0, then follow read_window.next_offset while has_more is true until the assigned evidence is found or the source is fully covered.',
    inputSchema: {
      id: { type: 'string', required: true },
      offset: { type: 'number', minimum: 0 },
      max_chars: { type: 'number', minimum: 256, maximum: MAX_MEMORY_READ_CHARS },
    },
    maxResultSizeChars: 3_900,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    validateInput: async input => {
      if (input.offset !== undefined && (!Number.isInteger(input.offset) || input.offset < 0)) {
        return { result: false, message: 'offset must be a non-negative integer' }
      }
      if (
        input.max_chars !== undefined &&
        (!Number.isInteger(input.max_chars) || input.max_chars < 256 || input.max_chars > MAX_MEMORY_READ_CHARS)
      ) {
        return { result: false, message: `max_chars must be an integer between 256 and ${MAX_MEMORY_READ_CHARS}` }
      }
      return { result: true }
    },
    async call(input) {
      const record = await store.read(input.id)
      if (!record) throw new Error(`Memory not found: ${input.id}`)
      const offset = input.offset ?? 0
      if (offset > record.content.length) {
        throw new Error(`offset ${offset} exceeds memory length ${record.content.length}`)
      }
      const maxChars = input.max_chars ?? DEFAULT_MEMORY_READ_CHARS
      const endOffset = Math.min(record.content.length, offset + maxChars)
      const hasMore = endOffset < record.content.length
      return {
        schema_version: record.schema_version,
        id: record.id,
        kind: record.kind,
        title: record.title,
        summary: record.summary,
        source: record.source,
        source_refs: record.source_refs,
        temporal: record.temporal,
        entities: record.entities,
        event_status: record.event_status,
        content: record.content.slice(offset, endOffset),
        read_window: {
          offset,
          end_offset: endOffset,
          total_chars: record.content.length,
          has_more: hasMore,
          next_offset: hasMore ? endOffset : null,
        },
      }
    },
  })

  const evidenceBundle = buildTool<EvidenceBundleInput, unknown>({
    name: 'MemoryEvidenceBundle',
    description: 'Compile a bounded, source-clustered evidence packet for a question. Preserves speaker roles and can prefer user or assistant excerpts without embeddings.',
    inputSchema: {
      query: { type: 'string', required: true },
      max_sources: { type: 'number' },
      max_chars: { type: 'number' },
      preferred_role: { type: 'string' },
    },
    maxResultSizeChars: 80_000,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    validateInput: async input => {
      if (!input.query.trim()) return { result: false, message: 'query must not be empty' }
      if (input.max_sources !== undefined && (!Number.isInteger(input.max_sources) || input.max_sources < 1 || input.max_sources > 30)) {
        return { result: false, message: 'max_sources must be an integer between 1 and 30' }
      }
      if (input.max_chars !== undefined && (!Number.isInteger(input.max_chars) || input.max_chars < 2_000 || input.max_chars > 80_000)) {
        return { result: false, message: 'max_chars must be an integer between 2000 and 80000' }
      }
      if (input.preferred_role !== undefined && !['user', 'assistant', 'any'].includes(input.preferred_role)) {
        return { result: false, message: 'preferred_role must be user, assistant, or any' }
      }
      return { result: true }
    },
    call: input => compileEvidenceBundle(store, input.query, {
      maxSources: input.max_sources,
      maxChars: input.max_chars,
      preferredRole: input.preferred_role,
    }),
  })

  const create = buildTool<CreateInput, unknown>({
    name: 'MemoryCreate',
    aliases: ['MemoryAppend'],
    description: 'Create a sourced, structured memory record.',
    inputSchema: {
      kind: { type: 'string', required: true },
      title: { type: 'string', required: true },
      summary: { type: 'string', required: true },
      content: { type: 'string', required: true },
      tags: { type: 'array', items: { type: 'string' } },
      source: { type: 'object', required: true },
      temporal: { type: 'object' },
      confidence: { type: 'number' },
      source_refs: { type: 'array', items: { type: 'string' } },
      entities: { type: 'array', items: { type: 'string' } },
      event_status: { type: 'string' },
      supersedes: { type: 'array', items: { type: 'string' } },
      relations: { type: 'array', items: { type: 'object' } },
    },
    validateInput: async input => validateKinds([input.kind]),
    call: input => store.create(input),
  })

  const update = buildTool<UpdateInput, unknown>({
    name: 'MemoryUpdate',
    description: 'Update a memory with optimistic revision checking and an audit source.',
    inputSchema: {
      id: { type: 'string', required: true },
      source_ref: { type: 'string', required: true },
      expected_revision: { type: 'number' },
      source_refs: { type: 'array', items: { type: 'string' } },
      entities: { type: 'array', items: { type: 'string' } },
      event_status: { type: 'string' },
      supersedes: { type: 'array', items: { type: 'string' } },
      relations: { type: 'array', items: { type: 'object' } },
    },
    validateInput: async input => {
      if (input.status && !['active', 'superseded'].includes(input.status)) {
        return { result: false, message: 'status must be active or superseded' }
      }
      if (input.tags && !Array.isArray(input.tags)) {
        return { result: false, message: 'tags must be an array' }
      }
      if (input.event_status && !['pending', 'completed', 'cancelled', 'uncertain'].includes(input.event_status)) {
        return { result: false, message: 'event_status is invalid' }
      }
      return { result: true }
    },
    call: ({ id, ...changes }) => store.update(id, changes),
  })

  const remove = buildTool<DeleteInput, unknown>({
    name: 'MemoryDelete',
    description: 'Soft-delete a memory while retaining its audit history.',
    inputSchema: {
      id: { type: 'string', required: true },
      source_ref: { type: 'string', required: true },
    },
    call: input => store.delete(input.id, input.source_ref),
  })

  const removeDerived = buildTool<DeleteInput, unknown>({
    name: 'MemoryDeleteDerived',
    description: 'Soft-delete only a derived event, state, topic, or deferred record. Immutable evidence is never deleted.',
    inputSchema: {
      id: { type: 'string', required: true },
      source_ref: { type: 'string', required: true },
    },
    call: input => store.deleteDerived(input.id, input.source_ref),
  })

  return [catalogSearch, search, read, evidenceBundle, create, update, remove, removeDerived]
}

export function selectSourceBalancedHits(hits: readonly MemoryHit[], limit: number): MemoryHit[] {
  const selected: MemoryHit[] = []
  const seenSources = new Set<string>()
  for (const hit of hits) {
    if (selected.length >= limit) break
    if (seenSources.has(hit.source_ref)) continue
    selected.push(hit)
    seenSources.add(hit.source_ref)
  }
  if (selected.length >= limit) return selected
  for (const hit of hits) {
    if (selected.length >= limit) break
    if (!selected.includes(hit)) selected.push(hit)
  }
  return selected
}

function validateKinds(kinds: MemoryKind[] | undefined) {
  const allowed = new Set<MemoryKind>([
    'episodic',
    'semantic',
    'procedural',
    'working',
    'evidence',
    'event',
    'state',
    'topic',
    'deferred',
  ])
  if (kinds && (!Array.isArray(kinds) || kinds.some(kind => !allowed.has(kind)))) {
    return Promise.resolve({ result: false as const, message: 'kinds contains an invalid memory kind' })
  }
  return Promise.resolve({ result: true as const })
}

export const MEMORY_TOOL_RULES: Record<string, 'allow'> = {
  MemoryCatalogSearch: 'allow',
  MemorySearch: 'allow',
  MemoryRead: 'allow',
  MemoryEvidenceBundle: 'allow',
  MemoryCreate: 'allow',
  MemoryUpdate: 'allow',
  MemoryDelete: 'allow',
  MemoryDeleteDerived: 'allow',
}
