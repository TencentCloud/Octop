import type { FileMemoryStore } from './store.js'
import type { MemoryRecord } from './types.js'

export type ConversationTurn = {
  role: string
  content: string
}

export type FormConversationSessionInput = {
  sessionId: string
  sourceDate: string
  turns: readonly ConversationTurn[]
  tags?: readonly string[]
}

export type FormConversationSessionResult = {
  raw: MemoryRecord
  frontmatter: MemoryRecord
  events: MemoryRecord[]
}

type EpisodeFrontmatter = {
  schema_version: '1.0'
  layer: 'episode_frontmatter'
  session_id: string
  source_date: string
  raw_memory_id: string
  event_count_hint: number
  speakers: string[]
  turn_refs: string[]
}

const FRONTMATTER_SUMMARY_CHARS = 2_400
const EVENT_SUMMARY_CHARS = 600

/**
 * Forms lossless raw evidence plus compact, fully sourced navigation records.
 * The event layer is deliberately conservative: one turn becomes one candidate
 * event. Semantic merging remains a query-time evidence task.
 */
export async function formConversationSession(
  store: FileMemoryStore,
  input: FormConversationSessionInput,
): Promise<FormConversationSessionResult> {
  const sourceDate = normalizeObservedAt(input.sourceDate)
  const turns = input.turns
    .map((turn, index) => ({
      role: normalizeRole(turn.role),
      content: turn.content.trim(),
      turnRef: `${input.sessionId}#turn-${index}`,
    }))
    .filter(turn => turn.content.length > 0)
  const baseTags = [...new Set([...(input.tags ?? []), 'memory-layer:raw'])]
  const rawContent = turns.map(turn => `${turn.role}: ${turn.content}`).join('\n')

  const raw = await store.create({
    kind: 'evidence',
    title: `Raw conversation ${input.sessionId}`,
    summary: `Immutable raw conversation with ${turns.length} sourced turns from ${input.sourceDate}.`,
    content: rawContent,
    tags: baseTags,
    source: { type: 'conversation', ref: input.sessionId, observed_at: sourceDate },
    source_refs: turns.map(turn => turn.turnRef),
    temporal: { event_time: input.sourceDate },
    confidence: 1,
  })

  const events = await Promise.all(turns.map(async (turn, index) => store.create({
    kind: 'event',
    title: `Turn ${index + 1} from ${input.sessionId}`,
    summary: compactText(turn.content, EVENT_SUMMARY_CHARS),
    content: `${turn.role}: ${turn.content}`,
    tags: [...new Set([...(input.tags ?? []), 'memory-layer:event', `speaker:${turn.role}`])],
    source: { type: 'conversation', ref: input.sessionId, observed_at: sourceDate },
    source_refs: [raw.id, turn.turnRef],
    temporal: { event_time: input.sourceDate },
    event_status: 'uncertain',
    relations: [{ type: 'derived_from', target: raw.id }],
    confidence: 1,
  })))

  const metadata: EpisodeFrontmatter = {
    schema_version: '1.0',
    layer: 'episode_frontmatter',
    session_id: input.sessionId,
    source_date: input.sourceDate,
    raw_memory_id: raw.id,
    event_count_hint: events.length,
    speakers: [...new Set(turns.map(turn => turn.role))],
    turn_refs: turns.map(turn => turn.turnRef),
  }
  const frontmatter = await store.create({
    kind: 'topic',
    title: `Episode frontmatter ${input.sessionId}`,
    summary: compactText(
      turns.map(turn => `[${turn.role}] ${compactText(turn.content, 160)}`).join(' | '),
      FRONTMATTER_SUMMARY_CHARS,
    ),
    content: JSON.stringify(metadata),
    tags: [...new Set([...(input.tags ?? []), 'memory-layer:frontmatter'])],
    source: { type: 'conversation', ref: input.sessionId, observed_at: sourceDate },
    source_refs: [raw.id, ...turns.map(turn => turn.turnRef)],
    temporal: { event_time: input.sourceDate },
    relations: [{ type: 'derived_from', target: raw.id }],
    confidence: 1,
  })

  return { raw, frontmatter, events }
}

function normalizeRole(value: string): string {
  const role = value.trim().toLowerCase()
  return role || 'unknown'
}

function normalizeObservedAt(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? new Date(0).toISOString() : parsed.toISOString()
}

function compactText(value: string, maxChars: number): string {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length <= maxChars) return compact
  return `${compact.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`
}
