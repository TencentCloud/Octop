export type EvidenceCandidateDecision = 'include' | 'exclude' | 'uncertain'
export type EvidenceCoverageStatus = 'complete' | 'incomplete' | 'uncertain'
export type EvidenceCoverageStopReason =
  | 'assigned_scope_exhausted'
  | 'relevant_sources_exhausted'
  | 'two_searches_no_new_source'
  | 'budget_exhausted'
  | 'unresolved_sources'
  | 'unread_memory'
  | 'not_applicable'

export type EvidenceCoverageDecision = {
  inspected_source_refs: string[]
  unresolved_source_refs: string[]
  stop_reason: EvidenceCoverageStopReason
}

export type EvidenceCandidate = {
  id: string
  claim: string
  decision: EvidenceCandidateDecision
  source_refs: string[]
  memory_ids: string[]
  source_date?: string
  event_time?: string
  duplicate_of?: string
  reason?: string
}

export type StructuredEvidenceResult = {
  schema_version: '1.0' | '1.1'
  task: string
  candidates: EvidenceCandidate[]
  covered_memory_ids: string[]
  covered_source_refs: string[]
  unexplored_source_refs: string[]
  conflicts: string[]
  missing_information: string[]
  coverage_status: EvidenceCoverageStatus
  coverage?: EvidenceCoverageDecision
}

export type ParsedEvidenceResult = {
  valid: boolean
  factValid: boolean
  coverageComplete: boolean
  result: StructuredEvidenceResult | null
  errors: string[]
  factErrors: string[]
  coverageErrors: string[]
}

export type EvidenceCoverageObservation = {
  assigned_source_refs: string[]
  inspected_source_refs: string[]
  unread_source_refs: string[]
  search_calls: number
  trailing_searches_without_new_sources: number
  bundle_truncated: boolean
  max_turns_exceeded: boolean
}

const DECISIONS = new Set<EvidenceCandidateDecision>(['include', 'exclude', 'uncertain'])
const COVERAGE = new Set<EvidenceCoverageStatus>(['complete', 'incomplete', 'uncertain'])
const COVERAGE_STOP_REASONS = new Set<EvidenceCoverageStopReason>([
  'assigned_scope_exhausted',
  'relevant_sources_exhausted',
  'two_searches_no_new_source',
  'budget_exhausted',
  'unresolved_sources',
  'unread_memory',
  'not_applicable',
])
const COMPLETE_STOP_REASONS = new Set<EvidenceCoverageStopReason>([
  'assigned_scope_exhausted',
  'relevant_sources_exhausted',
  'two_searches_no_new_source',
])

export function parseEvidenceResult(raw: string): ParsedEvidenceResult {
  let value: unknown
  try {
    value = JSON.parse(extractJson(raw))
  } catch (error) {
    const recovered = recoverTruncatedEvidenceResult(raw)
    const factErrors = [
      `invalid JSON: ${error instanceof Error ? error.message : String(error)}`,
      ...(recovered ? [`recovered ${recovered.candidates.length} complete sourced candidates from truncated output`] : []),
    ]
    return {
      valid: false,
      factValid: false,
      coverageComplete: false,
      result: recovered,
      errors: factErrors,
      factErrors,
      coverageErrors: [],
    }
  }
  if (!isRecord(value)) {
    const factErrors = ['evidence result must be an object']
    return {
      valid: false,
      factValid: false,
      coverageComplete: false,
      result: null,
      errors: factErrors,
      factErrors,
      coverageErrors: [],
    }
  }

  const factErrors: string[] = []
  const coverageErrors: string[] = []
  const schemaVersion = value.schema_version === '1.1' ? '1.1' : '1.0'
  const candidates = recordArray(value.candidates, 'candidates', factErrors)
    .map((candidate, index) => parseCandidate(candidate, index, factErrors))
  const coverageDecision = schemaVersion === '1.1'
    ? parseCoverageDecision(value.coverage, coverageErrors)
    : undefined
  const conflicts = schemaVersion === '1.1'
    ? optionalStringArray(value.conflicts, 'conflicts', factErrors)
    : stringArray(value.conflicts, 'conflicts', factErrors)
  const missingInformation = schemaVersion === '1.1'
    ? optionalStringArray(value.missing_information, 'missing_information', factErrors)
    : stringArray(value.missing_information, 'missing_information', factErrors)
  const coverage = coverageDecision
    ? coverageStatusFromDecision(coverageDecision)
    : enumValue(value.coverage_status, COVERAGE, 'coverage_status', coverageErrors, 'uncertain')
  const candidateMemoryIds = [...new Set(candidates.flatMap(candidate => candidate.memory_ids))]
  const candidateSourceRefs = [...new Set(candidates.flatMap(candidate => candidate.source_refs))]
  const result: StructuredEvidenceResult = {
    schema_version: schemaVersion,
    task: requiredString(value.task, 'task', factErrors),
    candidates,
    covered_memory_ids: schemaVersion === '1.1'
      ? candidateMemoryIds
      : stringArray(value.covered_memory_ids, 'covered_memory_ids', factErrors),
    covered_source_refs: schemaVersion === '1.1'
      ? [...new Set([...candidateSourceRefs, ...(coverageDecision?.inspected_source_refs ?? [])])]
      : stringArray(value.covered_source_refs, 'covered_source_refs', factErrors),
    unexplored_source_refs: schemaVersion === '1.1'
      ? coverageDecision?.unresolved_source_refs ?? []
      : stringArray(value.unexplored_source_refs, 'unexplored_source_refs', coverageErrors),
    conflicts,
    missing_information: missingInformation,
    coverage_status: coverage,
    ...(coverageDecision ? { coverage: coverageDecision } : {}),
  }
  if (value.schema_version !== '1.0' && value.schema_version !== '1.1') {
    factErrors.push('schema_version must be "1.0" or "1.1"')
  }
  if (
    coverageDecision &&
    COMPLETE_STOP_REASONS.has(coverageDecision.stop_reason) &&
    coverageDecision.unresolved_source_refs.length > 0
  ) {
    coverageErrors.push('an exhaustive coverage stop_reason cannot contain unresolved_source_refs')
  }
  if (
    coverageDecision &&
    coverageDecision.inspected_source_refs.some(ref => coverageDecision.unresolved_source_refs.includes(ref))
  ) {
    coverageErrors.push('a source_ref cannot be both inspected and unresolved')
  }
  if (coverage === 'complete' && result.unexplored_source_refs.length > 0) {
    coverageErrors.push('complete coverage cannot contain unexplored_source_refs')
    result.coverage_status = 'incomplete'
  }
  if (coverage === 'complete' && result.missing_information.some(describesUnreadMemoryWindow)) {
    coverageErrors.push('complete coverage cannot contain unread memory windows')
    result.coverage_status = 'incomplete'
  }
  const errors = [...factErrors, ...coverageErrors]
  return {
    valid: errors.length === 0,
    factValid: factErrors.length === 0,
    coverageComplete: result.coverage_status === 'complete' && coverageErrors.length === 0,
    result,
    errors,
    factErrors,
    coverageErrors,
  }
}

export function reconcileObservedEvidenceCoverage(
  parsed: ParsedEvidenceResult,
  observation: EvidenceCoverageObservation,
): ParsedEvidenceResult {
  if (!parsed.result) return parsed
  const modelCoverage = parsed.result.coverage
  const hasObservedScope = observation.assigned_source_refs.length > 0 ||
    observation.inspected_source_refs.length > 0 || observation.search_calls > 0
  const inspected = [...new Set(hasObservedScope
    ? observation.inspected_source_refs
    : modelCoverage?.inspected_source_refs ?? [])]
  const assignedButUnread = observation.assigned_source_refs.filter(ref => !inspected.includes(ref))
  const unresolved = [...new Set([
    ...assignedButUnread,
    ...observation.unread_source_refs,
    ...(modelCoverage?.unresolved_source_refs ?? []),
  ])].filter(ref => !observation.inspected_source_refs.includes(ref) || observation.unread_source_refs.includes(ref))

  let stopReason = modelCoverage?.stop_reason ?? 'not_applicable'
  if (observation.max_turns_exceeded) stopReason = 'budget_exhausted'
  else if (observation.unread_source_refs.length > 0) stopReason = 'unread_memory'
  else if (observation.bundle_truncated || unresolved.length > 0) stopReason = 'unresolved_sources'
  else if (
    observation.assigned_source_refs.length > 0 &&
    observation.assigned_source_refs.every(ref => inspected.includes(ref))
  ) stopReason = 'assigned_scope_exhausted'
  else if (
    observation.search_calls >= 2 &&
    observation.trailing_searches_without_new_sources >= 2
  ) stopReason = 'two_searches_no_new_source'

  const coverage: EvidenceCoverageDecision = {
    inspected_source_refs: inspected,
    unresolved_source_refs: unresolved,
    stop_reason: stopReason,
  }
  const observationErrors: string[] = []
  if (parsed.result.coverage_status === 'complete' && coverageStatusFromDecision(coverage) !== 'complete') {
    observationErrors.push('reported complete coverage conflicts with observed tool coverage')
  }
  const result: StructuredEvidenceResult = {
    ...parsed.result,
    covered_source_refs: [...new Set([...parsed.result.covered_source_refs, ...inspected])],
    unexplored_source_refs: unresolved,
    coverage_status: coverageStatusFromDecision(coverage),
    coverage,
  }
  return {
    valid: parsed.valid && observationErrors.length === 0,
    factValid: parsed.factValid,
    coverageComplete: result.coverage_status === 'complete' &&
      parsed.coverageErrors.length === 0 && observationErrors.length === 0,
    result,
    errors: [...parsed.errors, ...observationErrors],
    factErrors: parsed.factErrors,
    coverageErrors: [...parsed.coverageErrors, ...observationErrors],
  }
}

function parseCoverageDecision(value: unknown, errors: string[]): EvidenceCoverageDecision {
  if (!isRecord(value)) {
    errors.push('coverage must be an object for schema_version "1.1"')
    return {
      inspected_source_refs: [],
      unresolved_source_refs: [],
      stop_reason: 'not_applicable',
    }
  }
  return {
    inspected_source_refs: optionalStringArray(value.inspected_source_refs, 'coverage.inspected_source_refs', errors),
    unresolved_source_refs: optionalStringArray(value.unresolved_source_refs, 'coverage.unresolved_source_refs', errors),
    stop_reason: enumValue(
      value.stop_reason,
      COVERAGE_STOP_REASONS,
      'coverage.stop_reason',
      errors,
      'not_applicable',
    ),
  }
}

function coverageStatusFromDecision(coverage: EvidenceCoverageDecision): EvidenceCoverageStatus {
  if (coverage.unresolved_source_refs.length > 0) return 'incomplete'
  if (COMPLETE_STOP_REASONS.has(coverage.stop_reason)) return 'complete'
  if (coverage.stop_reason === 'budget_exhausted' || coverage.stop_reason === 'unread_memory' || coverage.stop_reason === 'unresolved_sources') {
    return 'incomplete'
  }
  return 'uncertain'
}

function describesUnreadMemoryWindow(value: string): boolean {
  return /\bunread\b|\bhas_more\b|\bnext_offset\b|\bremaining\s+(?:unread\s+)?content\b|\boffset\s+\d+\s+of\s+\d+/i.test(value)
}

function recoverTruncatedEvidenceResult(raw: string): StructuredEvidenceResult | null {
  const marker = raw.indexOf('"candidates"')
  const arrayStart = marker < 0 ? -1 : raw.indexOf('[', marker)
  if (arrayStart < 0) return null
  const objects = extractCompleteObjects(raw.slice(arrayStart + 1))
  const candidateErrors: string[] = []
  const candidates = objects.flatMap((object, index) => {
    try {
      const value = JSON.parse(object) as unknown
      if (!isRecord(value)) return []
      const localErrors: string[] = []
      const candidate = parseCandidate(value, index, localErrors)
      if (localErrors.length > 0) {
        candidateErrors.push(...localErrors)
        return []
      }
      return [candidate]
    } catch {
      return []
    }
  })
  if (candidates.length === 0) return null
  const taskMatch = raw.match(/"task"\s*:\s*("(?:\\.|[^"\\])*")/)
  let task = 'Recovered truncated evidence task'
  if (taskMatch?.[1]) {
    try { task = JSON.parse(taskMatch[1]) as string } catch { /* retain fallback */ }
  }
  return {
    schema_version: '1.0',
    task,
    candidates,
    covered_memory_ids: [...new Set(candidates.flatMap(candidate => candidate.memory_ids))],
    covered_source_refs: [...new Set(candidates.flatMap(candidate => candidate.source_refs))],
    unexplored_source_refs: [],
    conflicts: [],
    missing_information: ['The subagent output was truncated; only complete sourced candidates were recovered.'],
    coverage_status: 'uncertain',
  }
}

function extractCompleteObjects(value: string): string[] {
  const objects: string[] = []
  let start = -1
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = 0; index < value.length; index++) {
    const char = value[index]
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
      if (depth === 0) start = index
      depth++
    } else if (char === '}') {
      depth--
      if (depth === 0 && start >= 0) {
        objects.push(value.slice(start, index + 1))
        start = -1
      }
    } else if (char === ']' && depth === 0) {
      break
    }
  }
  return objects
}

function parseCandidate(candidate: Record<string, unknown>, index: number, errors: string[]): EvidenceCandidate {
  const sourceRefs = stringArray(candidate.source_refs, `candidates[${index}].source_refs`, errors)
  const memoryIds = stringArray(candidate.memory_ids, `candidates[${index}].memory_ids`, errors)
  const claim = requiredString(candidate.claim, `candidates[${index}].claim`, errors)
  const reason = typeof candidate.reason === 'string' ? candidate.reason.trim() : ''
  const parsedDecision = enumValue(candidate.decision, DECISIONS, `candidates[${index}].decision`, errors, 'uncertain')
  if (sourceRefs.length === 0) errors.push(`candidates[${index}] requires at least one source_ref`)
  if (memoryIds.length === 0) errors.push(`candidates[${index}] requires at least one memory_id`)
  return {
    id: requiredString(candidate.id, `candidates[${index}].id`, errors),
    claim,
    decision: normalizeExplicitObligationDecision(parsedDecision, claim, reason),
    source_refs: sourceRefs,
    memory_ids: memoryIds,
    ...optionalString('source_date', candidate.source_date),
    ...optionalString('event_time', candidate.event_time),
    ...optionalString('duplicate_of', candidate.duplicate_of),
    ...optionalString('reason', candidate.reason),
  }
}

function normalizeExplicitObligationDecision(
  decision: EvidenceCandidateDecision,
  claim: string,
  reason: string,
): EvidenceCandidateDecision {
  if (decision !== 'uncertain') return decision
  const explicitObligation = /\b(?:still\s+)?(?:need(?:s|ed)?|have\s+to|must)\b[^.!?]{0,100}\b(?:return|pick\s*up|collect|drop\s*off|send\s+back)\b/i.test(claim)
  const explicitClosure = /\b(?:already|has|had|was|were)\s+(?:explicitly\s+)?(?:returned|picked\s*up|collected|completed|cancelled|canceled)\b/i.test(`${claim} ${reason}`)
  return explicitObligation && !explicitClosure ? 'include' : decision
}

function extractJson(raw: string): string {
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]
  if (fenced) return fenced.trim()
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  return start >= 0 && end > start ? raw.slice(start, end + 1) : raw.trim()
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function recordArray(value: unknown, field: string, errors: string[]): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    errors.push(`${field} must be an array`)
    return []
  }
  return value.flatMap((item, index) => {
    if (isRecord(item)) return [item]
    errors.push(`${field}[${index}] must be an object`)
    return []
  })
}

function stringArray(value: unknown, field: string, errors: string[]): string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
    errors.push(`${field} must be a string array`)
    return []
  }
  return [...new Set(value.map(item => item.trim()).filter(Boolean))]
}

function optionalStringArray(value: unknown, field: string, errors: string[]): string[] {
  if (value === undefined) return []
  return stringArray(value, field, errors)
}

function requiredString(value: unknown, field: string, errors: string[]): string {
  if (typeof value !== 'string' || !value.trim()) {
    errors.push(`${field} must be a non-empty string`)
    return ''
  }
  return value.trim()
}

function optionalString<K extends string>(key: K, value: unknown): { [P in K]?: string } {
  return typeof value === 'string' && value.trim() ? { [key]: value.trim() } as { [P in K]?: string } : {}
}

function enumValue<T extends string>(
  value: unknown,
  allowed: ReadonlySet<T>,
  field: string,
  errors: string[],
  fallback: T,
): T {
  if (typeof value === 'string' && allowed.has(value as T)) return value as T
  errors.push(`${field} is invalid`)
  return fallback
}
