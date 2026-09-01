import { randomUUID } from 'node:crypto'
import { appendFile, mkdir, readFile, readdir, rename, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type {
  EventStatus,
  MemoryAuditEntry,
  MemoryHit,
  MemoryKind,
  MemoryRelation,
  MemoryRecord,
  MemorySource,
  MemoryTemporal,
} from './types.js'

export type CreateMemoryInput = {
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

export type UpdateMemoryInput = Partial<
  Pick<MemoryRecord,
    | 'title'
    | 'summary'
    | 'content'
    | 'tags'
    | 'temporal'
    | 'confidence'
    | 'status'
    | 'source_refs'
    | 'entities'
    | 'event_status'
    | 'supersedes'
    | 'relations'
  >
> & { expected_revision?: number; source_ref: string }

export type SearchMemoryInput = {
  query: string
  kinds?: MemoryKind[]
  limit?: number
  includeSuperseded?: boolean
}

export class FileMemoryStore {
  readonly root: string
  private readonly recordsRoot: string
  private readonly auditPath: string
  private readonly kindRoots: Record<MemoryKind, string>

  constructor(root: string) {
    this.root = path.resolve(root)
    this.recordsRoot = path.join(this.root, 'records')
    this.auditPath = path.join(this.root, 'audit.jsonl')
    this.kindRoots = {
      episodic: this.recordsRoot,
      semantic: this.recordsRoot,
      procedural: this.recordsRoot,
      working: this.recordsRoot,
      evidence: path.join(this.root, 'evidence'),
      event: path.join(this.root, 'events'),
      state: path.join(this.root, 'state'),
      topic: path.join(this.root, 'topics'),
      deferred: path.join(this.root, 'deferred'),
    }
  }

  async initialize(): Promise<void> {
    await Promise.all([...new Set(Object.values(this.kindRoots))].map(root => mkdir(root, { recursive: true })))
  }

  async create(input: CreateMemoryInput): Promise<MemoryRecord> {
    validateCreateInput(input)
    const duplicate = (await this.listRecords()).find(record =>
      record.status === 'active' &&
      record.kind === input.kind &&
      record.source.ref === input.source.ref &&
      normalizeText(record.title) === normalizeText(input.title) &&
      normalizeText(record.content) === normalizeText(input.content),
    )
    if (duplicate) return duplicate

    const now = new Date().toISOString()
    const record: MemoryRecord = {
      schema_version: '2.0',
      id: randomUUID(),
      kind: input.kind,
      title: input.title.trim(),
      summary: input.summary.trim(),
      content: input.content.trim(),
      tags: normalizeTags(input.tags ?? []),
      source: input.source,
      source_refs: normalizeSourceRefs(input.source_refs ?? [], input.source.ref),
      temporal: input.temporal,
      entities: normalizeIdentifiers(input.entities ?? []),
      event_status: input.event_status,
      supersedes: normalizeIdentifiers(input.supersedes ?? []),
      relations: normalizeRelations(input.relations ?? []),
      confidence: clampConfidence(input.confidence ?? 1),
      status: 'active',
      revision: 1,
      created_at: now,
      updated_at: now,
    }
    await this.writeRecord(record)
    await this.audit({
      timestamp: now,
      operation: 'create',
      memory_id: record.id,
      revision: record.revision,
      source_ref: input.source.ref,
    })
    return record
  }

  async read(id: string, includeDeleted = false): Promise<MemoryRecord | null> {
    assertMemoryId(id)
    for (const root of [...new Set(Object.values(this.kindRoots))]) {
      try {
        const raw = JSON.parse(await readFile(path.join(root, `${id}.json`), 'utf8')) as Partial<MemoryRecord>
        const record = normalizeRecord(raw)
        return record.status === 'deleted' && !includeDeleted ? null : record
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue
        throw error
      }
    }
    return null
  }

  async update(id: string, input: UpdateMemoryInput): Promise<MemoryRecord> {
    const current = await this.requireRecord(id)
    if (input.expected_revision !== undefined && input.expected_revision !== current.revision) {
      throw new Error(`Revision conflict: expected ${input.expected_revision}, found ${current.revision}`)
    }
    if (!input.source_ref?.trim()) throw new Error('source_ref is required for memory updates')
    if (current.kind === 'evidence') {
      throw new Error('Evidence memories are immutable; create a derived event, state, or topic instead')
    }

    const mutableFields = [
      'title',
      'summary',
      'content',
      'tags',
      'temporal',
      'confidence',
      'status',
      'source_refs',
      'entities',
      'event_status',
      'supersedes',
      'relations',
    ] as const
    const changes = mutableFields.filter(field => input[field] !== undefined)
    if (changes.length === 0) throw new Error('memory update contains no changes')

    const now = new Date().toISOString()
    const updated: MemoryRecord = {
      ...current,
      ...Object.fromEntries(changes.map(field => [field, input[field]])),
      tags: input.tags ? normalizeTags(input.tags) : current.tags,
      source_refs: input.source_refs
        ? normalizeSourceRefs(input.source_refs, input.source_ref)
        : normalizeSourceRefs(current.source_refs, input.source_ref),
      entities: input.entities ? normalizeIdentifiers(input.entities) : current.entities,
      supersedes: input.supersedes ? normalizeIdentifiers(input.supersedes) : current.supersedes,
      relations: input.relations ? normalizeRelations(input.relations) : current.relations,
      confidence: input.confidence === undefined ? current.confidence : clampConfidence(input.confidence),
      revision: current.revision + 1,
      updated_at: now,
    }
    await this.writeRecord(updated)
    await this.audit({
      timestamp: now,
      operation: 'update',
      memory_id: id,
      revision: updated.revision,
      source_ref: input.source_ref,
      changes: [...changes],
    })
    return updated
  }

  async delete(id: string, sourceRef: string): Promise<MemoryRecord> {
    if (!sourceRef.trim()) throw new Error('source_ref is required for memory deletion')
    const current = await this.requireRecord(id)
    if (current.kind === 'evidence') {
      throw new Error('Evidence memories are immutable and cannot be deleted')
    }
    const updated: MemoryRecord = {
      ...current,
      status: 'deleted',
      revision: current.revision + 1,
      updated_at: new Date().toISOString(),
    }
    await this.writeRecord(updated)
    await this.audit({
      timestamp: updated.updated_at,
      operation: 'delete',
      memory_id: id,
      revision: updated.revision,
      source_ref: sourceRef,
    })
    return updated
  }

  async deleteDerived(id: string, sourceRef: string): Promise<MemoryRecord> {
    const current = await this.requireRecord(id)
    if (!['event', 'state', 'topic', 'deferred'].includes(current.kind)) {
      throw new Error(`MemoryDeleteDerived only accepts event, state, topic, or deferred records; found ${current.kind}`)
    }
    return this.delete(id, sourceRef)
  }

  async search(input: SearchMemoryInput): Promise<MemoryHit[]> {
    const records = await this.listRecords()
    const queryTokens = tokenize(input.query)
    const allowedKinds = input.kinds ? new Set(input.kinds) : null
    const scored = records
      .filter(record => record.status === 'active' || (input.includeSuperseded && record.status === 'superseded'))
      .filter(record => !allowedKinds || allowedKinds.has(record.kind))
      .map(record => ({ record, score: scoreRecord(record, queryTokens) }))
      .filter(item => queryTokens.length === 0 || item.score > 0)
      .sort((a, b) => b.score - a.score || b.record.updated_at.localeCompare(a.record.updated_at))
      .slice(0, Math.max(1, Math.min(input.limit ?? 10, 50)))

    return scored.map(({ record, score }) => ({
      id: record.id,
      kind: record.kind,
      title: record.title,
      summary: record.summary,
      summary_complete: record.kind === 'event' && normalizeText(record.summary) === normalizeText(
        record.content.replace(/^[^:]+:\s*/, ''),
      ),
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
      score,
    }))
  }

  async findBySourcePrefix(prefix: string, limit = 20): Promise<MemoryRecord[]> {
    const normalized = prefix.trim()
    if (!normalized) return []
    return (await this.listRecords())
      .filter(record => record.status === 'active' && record.source.ref.startsWith(normalized))
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .slice(0, Math.max(1, Math.min(limit, 50)))
  }

  private async listRecords(): Promise<MemoryRecord[]> {
    await this.initialize()
    const roots = [...new Set(Object.values(this.kindRoots))]
    const records = await Promise.all(roots.map(async root => {
      const files = (await readdir(root)).filter(file => file.endsWith('.json'))
      return Promise.all(files.map(async file =>
        normalizeRecord(JSON.parse(await readFile(path.join(root, file), 'utf8')) as Partial<MemoryRecord>),
      ))
    }))
    return records.flat()
  }

  private async requireRecord(id: string): Promise<MemoryRecord> {
    const record = await this.read(id, true)
    if (!record) throw new Error(`Memory not found: ${id}`)
    return record
  }

  private recordPath(id: string, kind: MemoryKind): string {
    assertMemoryId(id)
    return path.join(this.kindRoots[kind], `${id}.json`)
  }

  private async writeRecord(record: MemoryRecord): Promise<void> {
    await this.initialize()
    const target = this.recordPath(record.id, record.kind)
    const temporary = `${target}.${randomUUID()}.tmp`
    await writeFile(temporary, `${JSON.stringify(record, null, 2)}\n`, 'utf8')
    await rename(temporary, target)
  }

  private async audit(entry: MemoryAuditEntry): Promise<void> {
    await this.initialize()
    await appendFile(this.auditPath, `${JSON.stringify(entry)}\n`, 'utf8')
  }
}

function validateCreateInput(input: CreateMemoryInput): void {
  if (!MEMORY_KINDS.includes(input.kind)) throw new Error(`Invalid memory kind: ${input.kind}`)
  for (const field of ['title', 'summary', 'content'] as const) {
    if (!input[field]?.trim()) throw new Error(`${field} must not be empty`)
  }
  if (!input.source?.ref?.trim() || !input.source.observed_at || !input.source.type) {
    throw new Error('memory source requires type, ref, and observed_at')
  }
  if (input.kind === 'event' && !input.temporal?.event_time && !input.temporal?.valid_from) {
    throw new Error('event memories require temporal.event_time or temporal.valid_from')
  }
  if (input.kind === 'state' && (input.source_refs?.length ?? 0) === 0) {
    throw new Error('state memories require source_refs to supporting evidence or events')
  }
  if (input.event_status && !EVENT_STATUSES.includes(input.event_status)) {
    throw new Error(`Invalid event status: ${input.event_status}`)
  }
}

const MEMORY_KINDS: MemoryKind[] = [
  'episodic',
  'semantic',
  'procedural',
  'working',
  'evidence',
  'event',
  'state',
  'topic',
  'deferred',
]

const EVENT_STATUSES: EventStatus[] = ['pending', 'completed', 'cancelled', 'uncertain']

function assertMemoryId(id: string): void {
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error(`Invalid memory id: ${id}`)
}

function normalizeTags(tags: string[]): string[] {
  return [...new Set(tags.map(tag => tag.trim().toLowerCase()).filter(Boolean))]
}

function normalizeIdentifiers(values: string[]): string[] {
  return [...new Set(values.map(value => value.trim()).filter(Boolean))]
}

function normalizeSourceRefs(values: string[], fallback: string): string[] {
  return normalizeIdentifiers([...values, fallback])
}

function normalizeRelations(relations: MemoryRelation[]): MemoryRelation[] {
  const allowed = new Set(['supports', 'contradicts', 'updates', 'derived_from', 'related'])
  const seen = new Set<string>()
  return relations.flatMap(relation => {
    if (!allowed.has(relation.type) || !relation.target?.trim()) return []
    const key = `${relation.type}:${relation.target.trim()}`
    if (seen.has(key)) return []
    seen.add(key)
    return [{ type: relation.type, target: relation.target.trim() }]
  })
}

function normalizeRecord(raw: Partial<MemoryRecord>): MemoryRecord {
  if (!raw.id || !raw.kind || !raw.title || !raw.summary || raw.content === undefined || !raw.source) {
    throw new Error('Invalid memory record on disk')
  }
  return {
    schema_version: '2.0',
    id: raw.id,
    kind: raw.kind,
    title: raw.title,
    summary: raw.summary,
    content: raw.content,
    tags: raw.tags ?? [],
    source: raw.source,
    source_refs: normalizeSourceRefs(raw.source_refs ?? [], raw.source.ref),
    temporal: raw.temporal,
    entities: normalizeIdentifiers(raw.entities ?? []),
    event_status: raw.event_status,
    supersedes: normalizeIdentifiers(raw.supersedes ?? []),
    relations: normalizeRelations(raw.relations ?? []),
    confidence: raw.confidence ?? 1,
    status: raw.status ?? 'active',
    revision: raw.revision ?? 1,
    created_at: raw.created_at ?? raw.source.observed_at,
    updated_at: raw.updated_at ?? raw.source.observed_at,
  }
}

function normalizeText(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function clampConfidence(value: number): number {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error('confidence must be between 0 and 1')
  return value
}

function tokenize(value: string): string[] {
  const normalized = value.toLowerCase()
  const tokens = normalized.match(/[\p{L}\p{N}_-]+/gu) ?? []
  const expanded = tokens.flatMap(token => {
    if (!/[\p{Script=Han}]/u.test(token)) return [token]
    const characters = [...token]
    const bigrams = characters.slice(0, -1).map((character, index) => character + characters[index + 1])
    return [token, ...characters, ...bigrams]
  })
  return [...new Set(expanded)]
}

function scoreRecord(record: MemoryRecord, queryTokens: string[]): number {
  if (queryTokens.length === 0) return record.confidence
  const fields = [
    record.title,
    record.summary,
    record.tags.join(' '),
    record.entities.join(' '),
    record.source_refs.join(' '),
    record.content,
  ].map(tokenize)
  const weights = [5, 4, 3, 3, 2, 1]
  let score = 0
  for (let index = 0; index < fields.length; index++) {
    const tokens = new Set(fields[index])
    score += queryTokens.filter(token => tokens.has(token)).length * weights[index]
  }
  return (score / (queryTokens.length * weights.reduce((sum, weight) => sum + weight, 0))) * record.confidence
}
