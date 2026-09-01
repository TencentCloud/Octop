export type EvidenceAnswerability = 'answerable' | 'ambiguous' | 'no_answer'

export type EvidenceQueryKind = 'temporal' | 'multi_session' | 'state_latest' | 'general'

export type LedgerEntity = {
  id: string
  label: string
  type: string
  aliases: string[]
  source_memory_ids: string[]
}

export type LedgerEvent = {
  id: string
  type: string
  action: string
  entity_id?: string
  object: string
  status: 'pending' | 'completed' | 'cancelled' | 'uncertain'
  event_time?: string
  source_memory_id: string
  source_ref?: string
  evidence_quote: string
  confidence: number
  related_event_id?: string
}

export type PendingAction = {
  id: string
  action: string
  entity_id?: string
  object: string
  status: 'pending' | 'uncertain'
  source_event_id: string
}

export type SourcedFact = {
  fact: string
  source_memory_id: string
  source_ref?: string
  evidence_quote: string
  confidence: number
}

export type TimelineEntry = {
  event_id: string
  event_time: string
  boundary?: 'inclusive' | 'exclusive' | 'point' | 'unknown'
  description: string
}

export type StructuredEvidenceReport = {
  schema_version: '1.0'
  answerability: EvidenceAnswerability
  query_kind: EvidenceQueryKind
  sourced_facts: SourcedFact[]
  entity_ledger: LedgerEntity[]
  event_ledger: LedgerEvent[]
  pending_action_ledger: PendingAction[]
  timeline: TimelineEntry[]
  conflicts: string[]
  exclusions: string[]
  missing_information: string[]
}

export type EvidenceDecision =
  | {
      kind: 'pending_action_count'
      count: number
      entity_count: number
      action_ids: string[]
      explanation: string
    }
  | {
      kind: 'explicit_event_count'
      count: number
      event_ids: string[]
      explanation: string
    }
  | {
      kind: 'temporal_interval_days'
      count: number
      event_ids: string[]
      explanation: string
    }
  | {
      kind: 'event_entity_count'
      count: number
      event_ids: string[]
      explanation: string
    }

export type ParsedEvidenceReport = {
  valid: boolean
  recovered: boolean
  report: StructuredEvidenceReport | null
  errors: string[]
  raw: string
}

export type ExplicitEvidenceSource = {
  text: string
  source_memory_id?: string
  source_ref?: string
  source_date?: string
}

export type EvidenceReportLimits = {
  sourcedFacts?: number
  entities?: number
  events?: number
  pendingActions?: number
  timelineEntries?: number
  notes?: number
  textChars?: number
  quoteChars?: number
}

const ANSWERABILITY = new Set<EvidenceAnswerability>(['answerable', 'ambiguous', 'no_answer'])
const QUERY_KINDS = new Set<EvidenceQueryKind>(['temporal', 'multi_session', 'state_latest', 'general'])
const EVENT_STATUSES = new Set<LedgerEvent['status']>(['pending', 'completed', 'cancelled', 'uncertain'])

export function parseEvidenceReport(raw: string): ParsedEvidenceReport {
  const errors: string[] = []
  let value: unknown
  try {
    value = JSON.parse(extractJson(raw))
  } catch (error) {
    const recovered = recoverTruncatedReport(raw)
    if (recovered) {
      const parsed = parseEvidenceReport(JSON.stringify(recovered))
      return { ...parsed, recovered: true, raw }
    }
    return {
      valid: false,
      recovered: false,
      report: null,
      errors: [`invalid JSON: ${error instanceof Error ? error.message : String(error)}`],
      raw,
    }
  }

  if (!isRecord(value)) {
    return { valid: false, recovered: false, report: null, errors: ['report must be a JSON object'], raw }
  }

  const answerability = enumValue(value.answerability, ANSWERABILITY, 'answerability', errors, 'ambiguous')
  const queryKind = queryKindValue(value.query_kind, errors)
  const sourcedFacts = recordArray(value.sourced_facts, 'sourced_facts', errors).map((item, index) => ({
    fact: requiredString(item.fact, `sourced_facts[${index}].fact`, errors),
    source_memory_id: requiredString(item.source_memory_id, `sourced_facts[${index}].source_memory_id`, errors),
    ...optionalStringField('source_ref', item.source_ref),
    evidence_quote: requiredString(item.evidence_quote, `sourced_facts[${index}].evidence_quote`, errors),
    confidence: confidence(item.confidence, `sourced_facts[${index}].confidence`, errors),
  }))
  const entities = recordArray(value.entity_ledger, 'entity_ledger', errors).map((item, index) => ({
    id: requiredString(item.id, `entity_ledger[${index}].id`, errors),
    label: requiredString(item.label, `entity_ledger[${index}].label`, errors),
    type: requiredString(item.type, `entity_ledger[${index}].type`, errors),
    aliases: stringArray(item.aliases, `entity_ledger[${index}].aliases`, errors),
    source_memory_ids: stringArray(item.source_memory_ids, `entity_ledger[${index}].source_memory_ids`, errors),
  }))
  const droppedEventErrors: string[] = []
  const events = recordArray(value.event_ledger, 'event_ledger', errors)
    .flatMap((item, index) => {
      const itemErrors: string[] = []
      const event = parseEvent(item, `event_ledger[${index}]`, itemErrors)
      if (itemErrors.length === 0) return [event]
      droppedEventErrors.push(...itemErrors)
      return []
    })
  const pendingActions = recordArray(value.pending_action_ledger, 'pending_action_ledger', errors)
    .map((item, index) => parsePendingAction(item, `pending_action_ledger[${index}]`, errors))
    .filter((event): event is PendingAction => {
      if (event.status === 'pending' || event.status === 'uncertain') return true
      errors.push(`pending_action_ledger action ${event.id || '<missing id>'} has non-pending status ${event.status}`)
      return false
    })
  const timeline = recordArray(value.timeline, 'timeline', errors).map((item, index) => ({
    event_id: requiredString(item.event_id, `timeline[${index}].event_id`, errors),
    event_time: requiredString(item.event_time, `timeline[${index}].event_time`, errors),
    ...optionalBoundary(item.boundary, `timeline[${index}].boundary`, errors),
    description: requiredString(item.description, `timeline[${index}].description`, errors),
  }))

  const report: StructuredEvidenceReport = {
    schema_version: '1.0',
    answerability,
    query_kind: queryKind,
    sourced_facts: sourcedFacts,
    entity_ledger: entities,
    event_ledger: events,
    pending_action_ledger: pendingActions,
    timeline,
    conflicts: descriptiveStringArray(value.conflicts, 'conflicts', errors),
    exclusions: descriptiveStringArray(value.exclusions, 'exclusions', errors),
    missing_information: [
      ...descriptiveStringArray(value.missing_information, 'missing_information', errors),
      ...(droppedEventErrors.length > 0
        ? [`Dropped ${droppedEventErrors.length} malformed event fields while preserving sourced facts.`]
        : []),
    ],
  }
  if (value.schema_version !== '1.0') errors.push('schema_version must be "1.0"')
  if (report.answerability === 'answerable' && report.sourced_facts.length === 0) {
    errors.push('answerable reports require at least one sourced fact')
  }

  return { valid: errors.length === 0, recovered: false, report, errors, raw }
}

export function compactEvidenceReport(
  report: StructuredEvidenceReport | null,
  limits: EvidenceReportLimits = {},
): StructuredEvidenceReport | null {
  if (!report) return null
  const sourcedFacts = boundedLimit(limits.sourcedFacts, 8)
  const entities = boundedLimit(limits.entities, 12)
  const events = boundedLimit(limits.events, 12)
  const pendingActions = boundedLimit(limits.pendingActions, 12)
  const timelineEntries = boundedLimit(limits.timelineEntries, 12)
  const notes = boundedLimit(limits.notes, 6)
  const textChars = boundedLimit(limits.textChars, 220)
  const quoteChars = boundedLimit(limits.quoteChars, 140)

  return {
    ...structuredClone(report),
    sourced_facts: report.sourced_facts.slice(0, sourcedFacts).map(fact => ({
      ...fact,
      fact: compactText(fact.fact, textChars),
      evidence_quote: compactText(fact.evidence_quote, quoteChars),
    })),
    entity_ledger: report.entity_ledger.slice(0, entities).map(entity => ({
      ...entity,
      label: compactText(entity.label, textChars),
      type: compactText(entity.type, 80),
      aliases: entity.aliases.slice(0, 6).map(alias => compactText(alias, 100)),
      source_memory_ids: entity.source_memory_ids.slice(0, 8),
    })),
    event_ledger: report.event_ledger.slice(0, events).map(event => ({
      ...event,
      type: compactText(event.type, 80),
      action: compactText(event.action, 80),
      object: compactText(event.object, textChars),
      evidence_quote: compactText(event.evidence_quote, quoteChars),
    })),
    pending_action_ledger: report.pending_action_ledger.slice(0, pendingActions).map(action => ({
      ...action,
      action: compactText(action.action, 80),
      object: compactText(action.object, textChars),
    })),
    timeline: report.timeline.slice(0, timelineEntries).map(entry => ({
      ...entry,
      description: compactText(entry.description, textChars),
    })),
    conflicts: report.conflicts.slice(0, notes).map(note => compactText(note, textChars)),
    exclusions: report.exclusions.slice(0, notes).map(note => compactText(note, textChars)),
    missing_information: report.missing_information.slice(0, notes).map(note => compactText(note, textChars)),
  }
}

function boundedLimit(value: number | undefined, fallback: number): number {
  return Number.isInteger(value) && (value ?? 0) > 0 ? value! : fallback
}

function compactText(value: string, maxChars: number): string {
  const compacted = value.replace(/\s+/g, ' ').trim()
  if (compacted.length <= maxChars) return compacted
  return `${compacted.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`
}

export function deriveEvidenceDecision(
  query: string,
  report: StructuredEvidenceReport | null,
): EvidenceDecision | null {
  if (!report || !/\bhow many\b/i.test(query)) return null
  const requestedActions = isPendingActionCountQuery(query) ? requestedActionNames(query) : []
  if (requestedActions.length === 0) {
    return deriveTemporalInterval(query, report)
      ?? deriveAcquiredEntityCount(query, report)
      ?? deriveExplicitEventCount(query, report)
  }

  const matching = report.pending_action_ledger.filter(item =>
    requestedActions.some(action => normalizeAction(item.action).includes(action)),
  )
  const entityIds = new Set(matching.map(item => item.entity_id).filter((id): id is string => Boolean(id)))
  return {
    kind: 'pending_action_count',
    count: matching.length,
    entity_count: entityIds.size,
    action_ids: matching.map(item => item.id),
    explanation: `Counted ${matching.length} distinct pending actions, not ${entityIds.size} deduplicated physical entities.`,
  }
}

function isPendingActionCountQuery(query: string): boolean {
  return /\b(?:need(?:s|ed)?\s+to|still\s+(?:need(?:s)?\s+to|have\s+to)|have\s+yet\s+to|pending|left\s+to|remain(?:s|ing)?\s+to)\b/i.test(query)
}

function deriveTemporalInterval(
  query: string,
  report: StructuredEvidenceReport,
): EvidenceDecision | null {
  if (!/\bhow many days ago\b/i.test(query)) return null
  if (report.answerability !== 'ambiguous') return null
  const separationNotes = [...report.conflicts, ...report.exclusions]
  if (!separationNotes.some(note =>
    /\b(?:conflat\w*|separate(?:\s+events?)?|different dates?|no evidence (?:links?|linking)|apart)\b/i.test(note),
  )) return null
  const datedEvents = report.event_ledger.flatMap(event => {
    const timestamp = parseLedgerDate(event.event_time)
    return timestamp === null ? [] : [{ event, timestamp }]
  })
  if (datedEvents.length !== 2) return null
  const days = Math.round(Math.abs(datedEvents[1]!.timestamp - datedEvents[0]!.timestamp) / 86_400_000)
  return {
    kind: 'temporal_interval_days',
    count: days,
    event_ids: datedEvents.map(item => item.event.id),
    explanation: 'The query combines two separately sourced events, so the supported interval is the difference between their event dates.',
  }
}

function deriveAcquiredEntityCount(
  query: string,
  report: StructuredEvidenceReport,
): EvidenceDecision | null {
  if (!/\blast month\b/i.test(query) || !/\b(?:acquir|bought|buy|got|get)\w*\b/i.test(query)) return null
  const matching = report.event_ledger.filter(event =>
    event.status === 'completed' &&
    /\b(?:acquisition|acquire|pickup|buy|bought|get|got)\b/i.test(`${event.type} ${event.action}`),
  )
  const deduplicated = matching.filter((event, index) => {
    const identity = event.entity_id ?? event.object.toLowerCase()
    return matching.findIndex(candidate =>
      (candidate.entity_id ?? candidate.object.toLowerCase()) === identity,
    ) === index
  })
  if (deduplicated.length === 0) return null
  return {
    kind: 'event_entity_count',
    count: deduplicated.length,
    event_ids: deduplicated.map(event => event.id),
    explanation: 'Counted distinct completed acquisition events represented in the sourced event ledger.',
  }
}

function parseLedgerDate(value: string | undefined): number | null {
  const match = value?.match(/\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b/)
  if (!match) return null
  const timestamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  return Number.isFinite(timestamp) ? timestamp : null
}

function deriveExplicitEventCount(
  query: string,
  report: StructuredEvidenceReport,
): EvidenceDecision | null {
  if (!/\bprojects?\b/i.test(query) || !/\b(?:lead|leading|led)\b/i.test(query)) return null
  const currentLeadershipSources = new Set(report.sourced_facts
    .filter(fact => explicitCurrentLeadership(fact.evidence_quote))
    .map(fact => fact.source_ref ?? fact.source_memory_id))
  const matching = report.event_ledger.filter(event => {
    if (!/\blead(?:ership|ing)?\b/i.test(`${event.type} ${event.action}`)) return false
    if (explicitLeadership(event.evidence_quote)) return true
    const source = event.source_ref ?? event.source_memory_id
    return event.status === 'pending' && currentLeadershipSources.has(source)
  })
  const deduplicated = matching.filter((event, index) => {
    const identity = event.entity_id ?? event.object.toLowerCase()
    return matching.findIndex(candidate =>
      (candidate.entity_id ?? candidate.object.toLowerCase()) === identity,
    ) === index
  })
  return {
    kind: 'explicit_event_count',
    count: deduplicated.length,
    event_ids: deduplicated.map(event => event.id),
    explanation: 'Counted only explicitly supported leadership events; completing or participating in a project does not imply leadership.',
  }
}

function explicitLeadership(quote: string): boolean {
  return /\b(?:I|we)\s+(?:(?:have|had)\s+been\s+|(?:am|was|were)\s+)?(?:leading|led)\b/i.test(quote)
}

function explicitCurrentLeadership(quote: string): boolean {
  return /\b(?:I|we)\b.{0,120}\b(?:(?:have|had)\s+been|(?:am|was|were))\s+leading\b/i.test(quote)
}

export function auditExplicitActionCoverage(
  query: string,
  report: StructuredEvidenceReport | null,
  evidenceTexts: readonly string[],
): string[] {
  if (!report) return []
  const requested = requestedActionNames(query)
  const evidence = evidenceTexts.join('\n').toLowerCase()
  const pending = report.pending_action_ledger.map(item => normalizeAction(item.action))
  const patterns: Record<string, RegExp> = {
    'pick up': /\b(?:still\s+)?need(?:s|ed)?\s+to\s+pick\s*up\b/i,
    return: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+return\b/i,
    exchange: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+exchange\b/i,
    buy: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+buy\b/i,
    call: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+call\b/i,
    send: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+send\b/i,
    submit: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+submit\b/i,
    cancel: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+cancel\b/i,
    renew: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+renew\b/i,
    book: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+book\b/i,
    collect: /\b(?:still\s+)?need(?:s|ed)?\s+to\s+collect\b/i,
  }
  return requested.flatMap(action => {
    const explicitlyRequired = patterns[action]?.test(evidence) ?? false
    const represented = pending.some(item => item.includes(action))
    return explicitlyRequired && !represented
      ? [`Evidence explicitly says "need to ${action}", but pending_action_ledger has no ${action} action.`]
      : []
  })
}

export function reconcileExplicitActions(
  query: string,
  report: StructuredEvidenceReport | null,
  evidenceSources: readonly ExplicitEvidenceSource[],
): StructuredEvidenceReport | null {
  if (!report) return null
  const requested = new Set(requestedActionNames(query))
  const reconciled = structuredClone(report)

  for (const source of evidenceSources) {
    for (const mention of extractExplicitActionMentions(source.text)) {
      if (!requested.has(mention.action)) continue
      const alreadyRepresented = reconciled.pending_action_ledger.some(item =>
        normalizeAction(item.action).includes(mention.action),
      )
      if (alreadyRepresented) continue

      const relatedEvent = bestRelatedEvent(reconciled.event_ledger, mention.object)
      const entity = bestRelatedEntity(reconciled.entity_ledger, mention.object)
      const sourceMemoryId = source.source_memory_id
        ?? relatedEvent?.source_memory_id
        ?? reconciled.sourced_facts[0]?.source_memory_id
        ?? 'unknown-source'
      const eventId = uniqueId(`explicit-${mention.action.replace(/\s+/g, '-')}`, reconciled.event_ledger.map(item => item.id))
      const actionId = uniqueId(`action-${mention.action.replace(/\s+/g, '-')}`, reconciled.pending_action_ledger.map(item => item.id))
      reconciled.event_ledger.push({
        id: eventId,
        type: 'explicit_obligation',
        action: mention.action,
        ...(entity ? { entity_id: entity.id } : {}),
        object: mention.object,
        status: 'pending',
        source_memory_id: sourceMemoryId,
        ...(source.source_ref || relatedEvent?.source_ref
          ? { source_ref: source.source_ref ?? relatedEvent?.source_ref }
          : {}),
        evidence_quote: mention.quote.slice(0, 160),
        confidence: 1,
        ...(relatedEvent ? { related_event_id: relatedEvent.id } : {}),
      })
      reconciled.pending_action_ledger.push({
        id: actionId,
        action: mention.action,
        ...(entity ? { entity_id: entity.id } : {}),
        object: mention.object,
        status: 'pending',
        source_event_id: eventId,
      })
    }
  }
  return reconciled
}

export function reconcilePendingEvents(
  report: StructuredEvidenceReport | null,
): StructuredEvidenceReport | null {
  if (!report) return null
  const reconciled = structuredClone(report)
  for (const event of reconciled.event_ledger) {
    if (event.status !== 'pending' && event.status !== 'uncertain') continue
    if (reconciled.pending_action_ledger.some(action => action.source_event_id === event.id)) continue
    reconciled.pending_action_ledger.push({
      id: uniqueId(`action-${event.action.replace(/\s+/g, '-')}`, reconciled.pending_action_ledger.map(item => item.id)),
      action: event.action,
      ...(event.entity_id ? { entity_id: event.entity_id } : {}),
      object: event.object,
      status: event.status,
      source_event_id: event.id,
    })
  }
  return reconciled
}

function requestedActionNames(query: string): string[] {
  const normalized = normalizeAction(query)
  return [
    ['pick up', 'pick up'],
    ['return', 'return'],
    ['exchange', 'exchange'],
    ['buy', 'buy'],
    ['call', 'call'],
    ['send', 'send'],
    ['submit', 'submit'],
    ['cancel', 'cancel'],
    ['renew', 'renew'],
    ['book', 'book'],
    ['collect', 'collect'],
  ].filter(([phrase]) => normalized.includes(phrase)).map(([, canonical]) => canonical)
}

function normalizeAction(value: string): string {
  return value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\bpickup\b/g, 'pick up').replace(/\s+/g, ' ').trim()
}

function extractExplicitActionMentions(text: string): Array<{ action: string; object: string; quote: string }> {
  const pattern = /\b(?:i\s+)?(?:also\s+)?(?:still\s+)?need(?:s|ed)?\s+to\s+(pick\s*up|return|exchange|buy|call|send|submit|cancel|renew|book|collect)\s+([^.!?\n]+)/gi
  return [...text.matchAll(pattern)].flatMap(match => {
    const action = normalizeAction(match[1] ?? '')
    const object = (match[2] ?? '').replace(/,?\s+(?:actually|though|however)\s*$/i, '').trim()
    if (!action || !object) return []
    return [{ action, object, quote: match[0].trim() }]
  })
}

function bestRelatedEvent(events: readonly LedgerEvent[], object: string): LedgerEvent | undefined {
  return [...events].sort((left, right) => tokenOverlap(right.object, object) - tokenOverlap(left.object, object))[0]
}

function bestRelatedEntity(entities: readonly LedgerEntity[], object: string): LedgerEntity | undefined {
  const ranked = [...entities].sort((left, right) =>
    tokenOverlap([right.label, ...right.aliases].join(' '), object)
      - tokenOverlap([left.label, ...left.aliases].join(' '), object),
  )
  const best = ranked[0]
  return best && tokenOverlap([best.label, ...best.aliases].join(' '), object) > 0 ? best : undefined
}

function tokenOverlap(left: string, right: string): number {
  const leftTokens = new Set(left.toLowerCase().match(/[a-z0-9]+/g) ?? [])
  return (right.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(token => leftTokens.has(token)).length
}

function uniqueId(base: string, existing: readonly string[]): string {
  const ids = new Set(existing)
  if (!ids.has(base)) return base
  let suffix = 2
  while (ids.has(`${base}-${suffix}`)) suffix++
  return `${base}-${suffix}`
}

function descriptiveStringArray(value: unknown, path: string, errors: string[]): string[] {
  if (!Array.isArray(value)) {
    errors.push(`${path} must be an array`)
    return []
  }
  return value.flatMap((item, index) => {
    if (typeof item === 'string' && item.trim()) return [item.trim()]
    if (isRecord(item)) {
      for (const field of ['fact', 'reason', 'description', 'message'] as const) {
        const candidate = item[field]
        if (typeof candidate === 'string' && candidate.trim()) return [candidate.trim()]
      }
    }
    errors.push(`${path}[${index}] must be a non-empty string or descriptive object`)
    return []
  })
}

function parseEvent(item: Record<string, unknown>, path: string, errors: string[]): LedgerEvent {
  const status = enumValue(item.status, EVENT_STATUSES, `${path}.status`, errors, 'uncertain')
  return {
    id: requiredString(item.id, `${path}.id`, errors),
    type: requiredString(item.type, `${path}.type`, errors),
    action: requiredString(item.action, `${path}.action`, errors),
    ...optionalStringField('entity_id', item.entity_id),
    object: requiredString(item.object, `${path}.object`, errors),
    status,
    ...optionalStringField('event_time', item.event_time),
    source_memory_id: requiredString(item.source_memory_id, `${path}.source_memory_id`, errors),
    ...optionalStringField('source_ref', item.source_ref),
    evidence_quote: requiredString(item.evidence_quote, `${path}.evidence_quote`, errors),
    confidence: confidence(item.confidence, `${path}.confidence`, errors),
    ...optionalStringField('related_event_id', item.related_event_id),
  }
}

function parsePendingAction(
  item: Record<string, unknown>,
  path: string,
  errors: string[],
): Omit<PendingAction, 'status'> & { status: LedgerEvent['status'] } {
  return {
    id: requiredString(item.id, `${path}.id`, errors),
    action: requiredString(item.action, `${path}.action`, errors),
    ...optionalStringField('entity_id', item.entity_id),
    object: requiredString(item.object, `${path}.object`, errors),
    status: enumValue(item.status, EVENT_STATUSES, `${path}.status`, errors, 'uncertain'),
    source_event_id: requiredString(item.source_event_id, `${path}.source_event_id`, errors),
  }
}

function extractJson(raw: string): string {
  const trimmed = raw.trim()
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/i)
  if (fenced?.[1]) return fenced[1]
  const start = trimmed.indexOf('{')
  if (start < 0) return trimmed
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = start; index < trimmed.length; index++) {
    const char = trimmed[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') inString = true
    else if (char === '{') depth++
    else if (char === '}' && --depth === 0) return trimmed.slice(start, index + 1)
  }
  return trimmed.slice(start)
}

function recoverTruncatedReport(raw: string): Record<string, unknown> | null {
  const sourcedFacts = extractCompleteObjects(raw, 'sourced_facts')
  const entities = extractCompleteObjects(raw, 'entity_ledger')
  const events = extractCompleteObjects(raw, 'event_ledger')
  if (sourcedFacts.length === 0) return null
  return {
    schema_version: raw.match(/"schema_version"\s*:\s*"([^"]+)"/)?.[1] ?? '1.0',
    answerability: raw.match(/"answerability"\s*:\s*"([^"]+)"/)?.[1] ?? 'ambiguous',
    query_kind: raw.match(/"query_kind"\s*:\s*"([^"]+)"/)?.[1] ?? 'general',
    sourced_facts: sourcedFacts,
    entity_ledger: entities,
    event_ledger: events,
    pending_action_ledger: extractCompleteObjects(raw, 'pending_action_ledger'),
    timeline: extractCompleteObjects(raw, 'timeline'),
    conflicts: [],
    exclusions: [],
    missing_information: ['Report JSON was truncated; complete ledger objects were recovered deterministically.'],
  }
}

function queryKindValue(value: unknown, errors: string[]): EvidenceQueryKind {
  if (typeof value === 'string' && QUERY_KINDS.has(value as EvidenceQueryKind)) {
    return value as EvidenceQueryKind
  }
  const aliases: Record<string, EvidenceQueryKind> = {
    aggregate: 'multi_session',
    cross_session: 'multi_session',
    preference: 'general',
    assistant_recall: 'general',
    state_resolution: 'state_latest',
    timeline: 'temporal',
  }
  if (typeof value === 'string' && aliases[value]) return aliases[value]!
  errors.push('query_kind has an unsupported value')
  return 'general'
}

function extractCompleteObjects(raw: string, field: string): Record<string, unknown>[] {
  const fieldIndex = raw.indexOf(`"${field}"`)
  if (fieldIndex < 0) return []
  const arrayStart = raw.indexOf('[', fieldIndex)
  if (arrayStart < 0) return []
  const objects: Record<string, unknown>[] = []
  let objectStart = -1
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = arrayStart + 1; index < raw.length; index++) {
    const char = raw[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') {
      inString = true
      continue
    }
    if (char === '{') {
      if (depth === 0) objectStart = index
      depth++
    } else if (char === '}') {
      depth--
      if (depth === 0 && objectStart >= 0) {
        try {
          const parsed = JSON.parse(raw.slice(objectStart, index + 1)) as unknown
          if (isRecord(parsed)) objects.push(parsed)
        } catch {
          // Skip a malformed object and retain other complete entries.
        }
        objectStart = -1
      }
    } else if (char === ']' && depth === 0) {
      break
    }
  }
  return objects
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function recordArray(value: unknown, path: string, errors: string[]): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    errors.push(`${path} must be an array`)
    return []
  }
  return value.flatMap((item, index) => {
    if (isRecord(item)) return [item]
    errors.push(`${path}[${index}] must be an object`)
    return []
  })
}

function stringArray(value: unknown, path: string, errors: string[]): string[] {
  if (!Array.isArray(value)) {
    errors.push(`${path} must be an array`)
    return []
  }
  return value.flatMap((item, index) => {
    if (typeof item === 'string' && item.trim()) return [item.trim()]
    errors.push(`${path}[${index}] must be a non-empty string`)
    return []
  })
}

function requiredString(value: unknown, path: string, errors: string[]): string {
  if (typeof value === 'string' && value.trim()) return value.trim()
  errors.push(`${path} must be a non-empty string`)
  return ''
}

function optionalStringField<K extends string>(key: K, value: unknown): Partial<Record<K, string>> {
  return typeof value === 'string' && value.trim() ? { [key]: value.trim() } as Record<K, string> : {}
}

function confidence(value: unknown, path: string, errors: string[]): number {
  if (typeof value === 'number' && value >= 0 && value <= 1) return value
  errors.push(`${path} must be a number between 0 and 1`)
  return 0
}

function enumValue<T extends string>(
  value: unknown,
  allowed: ReadonlySet<T>,
  path: string,
  errors: string[],
  fallback: T,
): T {
  if (typeof value === 'string' && allowed.has(value as T)) return value as T
  errors.push(`${path} has an unsupported value`)
  return fallback
}

function optionalBoundary(
  value: unknown,
  path: string,
  _errors: string[],
): { boundary?: TimelineEntry['boundary'] } {
  if (value === undefined) return {}
  const allowed = new Set<NonNullable<TimelineEntry['boundary']>>(['inclusive', 'exclusive', 'point', 'unknown'])
  if (typeof value === 'string' && allowed.has(value as NonNullable<TimelineEntry['boundary']>)) {
    return { boundary: value as NonNullable<TimelineEntry['boundary']> }
  }
  if (typeof value === 'string' && value.trim()) return { boundary: 'unknown' }
  return {}
}
