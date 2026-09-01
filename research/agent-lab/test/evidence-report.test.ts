import assert from 'node:assert/strict'
import test from 'node:test'

import {
  auditExplicitActionCoverage,
  compactEvidenceReport,
  deriveEvidenceDecision,
  parseEvidenceReport,
  reconcileExplicitActions,
  reconcilePendingEvents,
} from '../src/memory/evidence-report.js'

test('structured report compression bounds verbose fields and ledger sizes', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'answerable', query_kind: 'multi_session',
    sourced_facts: Array.from({ length: 10 }, (_, index) => ({
      fact: `fact-${index} ${'detail '.repeat(80)}`,
      source_memory_id: `m${index}`,
      evidence_quote: `quote-${index} ${'evidence '.repeat(40)}`,
      confidence: 1,
    })),
    entity_ledger: [], event_ledger: [], pending_action_ledger: [], timeline: [],
    conflicts: Array.from({ length: 9 }, (_, index) => `conflict-${index} ${'detail '.repeat(80)}`),
    exclusions: [], missing_information: [],
  }))

  const compacted = compactEvidenceReport(parsed.report)

  assert.equal(compacted?.sourced_facts.length, 8)
  assert.equal(compacted?.conflicts.length, 6)
  assert.equal((compacted?.sourced_facts[0]?.fact.length ?? 0) <= 220, true)
  assert.equal((compacted?.sourced_facts[0]?.evidence_quote.length ?? 0) <= 140, true)
  assert.equal((compacted?.conflicts[0]?.length ?? 0) <= 220, true)
})

test('evidence ledger keeps entity identity separate from pending action identity', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0',
    answerability: 'answerable',
    query_kind: 'multi_session',
    sourced_facts: [{
      fact: 'The user must return old boots and pick up replacement boots and a blazer.',
      source_memory_id: 'memory-zara',
      source_ref: 'zara-session',
      evidence_quote: 'return the boots, pick up their replacement, and pick up the blazer',
      confidence: 1,
    }],
    entity_ledger: [
      { id: 'boots', label: 'boots', type: 'item', aliases: ['old boots', 'replacement boots'], source_memory_ids: ['memory-zara'] },
      { id: 'blazer', label: 'blazer', type: 'item', aliases: [], source_memory_ids: ['memory-zara'] },
    ],
    event_ledger: [
      event('return-boots', 'return', 'boots', 'old boots'),
      event('pickup-boots', 'pickup', 'boots', 'replacement boots'),
      event('pickup-blazer', 'pickup', 'blazer', 'blazer'),
    ],
    pending_action_ledger: [
      action('return-boots', 'return', 'boots', 'old boots'),
      action('pickup-boots', 'pickup', 'boots', 'replacement boots'),
      action('pickup-blazer', 'pickup', 'blazer', 'blazer'),
    ],
    timeline: [],
    conflicts: [],
    exclusions: [],
    missing_information: [],
  }))

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  const decision = deriveEvidenceDecision('How many items did I need to pick up or return?', parsed.report)
  assert.deepEqual(decision, {
    kind: 'pending_action_count',
    count: 3,
    entity_count: 2,
    action_ids: ['return-boots', 'pickup-boots', 'pickup-blazer'],
    explanation: 'Counted 3 distinct pending actions, not 2 deduplicated physical entities.',
  })
})

test('invalid free-text evidence reports are surfaced instead of silently trusted', () => {
  const parsed = parseEvidenceReport('answerability: answerable; probably three')
  assert.equal(parsed.valid, false)
  assert.equal(parsed.report, null)
  assert.match(parsed.errors[0] ?? '', /invalid JSON/)
})

test('report parser normalizes common compiler query-kind aliases', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'answerable', query_kind: 'aggregate',
    sourced_facts: [{ fact: 'Five sessions.', source_memory_id: 'm1', evidence_quote: 'five sessions', confidence: 1 }],
    entity_ledger: [], event_ledger: [], pending_action_ledger: [], timeline: [],
    conflicts: [], exclusions: [], missing_information: [],
  }))

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  assert.equal(parsed.report?.query_kind, 'multi_session')
})

test('truncated state reports recover from complete sourced facts without an event ledger', () => {
  const raw = '{"schema_version":"1.0","answerability":"answerable","query_kind":"state_latest","sourced_facts":[{"fact":"Previous best was 27:45.","source_memory_id":"m1","evidence_quote":"27 minutes and 45 seconds","confidence":1}],"entity_ledger":['
  const parsed = parseEvidenceReport(raw)

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  assert.equal(parsed.recovered, true)
  assert.equal(parsed.report?.sourced_facts[0]?.fact, 'Previous best was 27:45.')
})

test('semantic audit catches explicit obligations omitted from a pending-action ledger', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0',
    answerability: 'answerable',
    query_kind: 'multi_session',
    sourced_facts: [{ fact: 'Replacement boots need pickup.', source_memory_id: 'm1', evidence_quote: 'pick them up', confidence: 1 }],
    entity_ledger: [{ id: 'boots', label: 'boots', type: 'item', aliases: [], source_memory_ids: ['m1'] }],
    event_ledger: [event('pickup-boots', 'pickup', 'boots', 'replacement boots')],
    pending_action_ledger: [action('pickup-boots', 'pickup', 'boots', 'replacement boots')],
    timeline: [],
    conflicts: [],
    exclusions: [],
    missing_information: [],
  }))

  assert.deepEqual(auditExplicitActionCoverage(
    'How many items do I need to pick up or return?',
    parsed.report,
    ['I need to return some boots. I exchanged them for a larger size and still need to pick them up.'],
  ), ['Evidence explicitly says "need to return", but pending_action_ledger has no return action.'])
})

test('deterministic reconciliation restores an omitted explicit action with provenance', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0',
    answerability: 'answerable',
    query_kind: 'multi_session',
    sourced_facts: [{ fact: 'Replacement boots need pickup.', source_memory_id: 'm1', evidence_quote: 'pick them up', confidence: 1 }],
    entity_ledger: [{ id: 'boots', label: 'boots', type: 'item', aliases: ['replacement boots'], source_memory_ids: ['m1', 'm2'] }],
    event_ledger: [event('pickup-boots', 'pickup', 'boots', 'replacement boots')],
    pending_action_ledger: [action('pickup-boots', 'pickup', 'boots', 'replacement boots')],
    timeline: [], conflicts: [], exclusions: [], missing_information: [],
  }))
  const reconciled = reconcileExplicitActions(
    'How many items do I need to pick up or return?',
    parsed.report,
    [{ text: 'I need to return some boots to Zara, actually.', source_memory_id: 'm2', source_ref: 'session-return' }],
  )

  assert.equal(reconciled?.pending_action_ledger.length, 2)
  assert.equal(reconciled?.pending_action_ledger.at(-1)?.action, 'return')
  assert.equal(reconciled?.event_ledger.at(-1)?.source_memory_id, 'm2')
  assert.equal(reconciled?.event_ledger.at(-1)?.source_ref, 'session-return')
  assert.deepEqual(auditExplicitActionCoverage(
    'How many items do I need to pick up or return?',
    reconciled,
    ['I need to return some boots to Zara, actually.'],
  ), [])
})

test('truncated reports recover complete events and rebuild pending actions', () => {
  const raw = JSON.stringify({
    schema_version: '1.0',
    answerability: 'answerable',
    query_kind: 'multi_session',
    sourced_facts: [{ fact: 'A blazer pickup is pending.', source_memory_id: 'm1', evidence_quote: 'need to pick up blazer', confidence: 1 }],
    entity_ledger: [{ id: 'blazer', label: 'blazer', type: 'item', aliases: [], source_memory_ids: ['m1'] }],
    event_ledger: [event('pickup-blazer', 'pickup', 'blazer', 'navy blazer')],
    pending_action_ledger: [action('pickup-blazer', 'pickup', 'blazer', 'navy blazer')],
    timeline: [], conflicts: [], exclusions: [], missing_information: [],
  })
  const truncated = raw.slice(0, raw.indexOf('"pending_action_ledger"') + '"pending_action_ledger":['.length)
  const parsed = parseEvidenceReport(truncated)
  const reconciled = reconcilePendingEvents(parsed.report)

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  assert.equal(parsed.recovered, true)
  assert.equal(reconciled?.event_ledger.length, 1)
  assert.equal(reconciled?.pending_action_ledger.length, 1)
  assert.equal(reconciled?.pending_action_ledger[0]?.source_event_id, 'pickup-blazer')
})

test('explicit leadership count excludes projects merely completed by the user', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0',
    answerability: 'answerable',
    query_kind: 'multi_session',
    sourced_facts: [
      { fact: 'Led a class team.', source_memory_id: 'm1', source_ref: 'class', evidence_quote: 'I led the data analysis team.', confidence: 1 },
      { fact: 'Currently leads a team.', source_memory_id: 'm2', source_ref: 'work', evidence_quote: 'I was promoted and have been leading a team of five engineers.', confidence: 1 },
    ],
    entity_ledger: [
      { id: 'class-project', label: 'Class project', type: 'project', aliases: [], source_memory_ids: ['m1'] },
      { id: 'completed-project', label: 'Completed project', type: 'project', aliases: [], source_memory_ids: ['m2'] },
      { id: 'current-project', label: 'Feature launch', type: 'project', aliases: [], source_memory_ids: ['m2'] },
    ],
    event_ledger: [
      projectEvent('lead-class', 'class-project', 'class', 'I led the data analysis team.', 'completed'),
      projectEvent('completed-work', 'completed-project', 'work', 'I completed this project early, which led to more revenue.', 'completed'),
      projectEvent('current-work', 'current-project', 'work', 'I am planning the June feature launch.', 'pending'),
    ],
    pending_action_ledger: [],
    timeline: [{ event_id: 'current-work', event_time: '~2026-07', boundary: 'approximate', description: 'Approximate current project date.' }],
    conflicts: [], exclusions: [], missing_information: [],
  }))

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  assert.equal(parsed.report?.timeline[0]?.boundary, 'unknown')
  assert.deepEqual(deriveEvidenceDecision('How many projects have I led or am currently leading?', parsed.report), {
    kind: 'explicit_event_count',
    count: 2,
    event_ids: ['lead-class', 'current-work'],
    explanation: 'Counted only explicitly supported leadership events; completing or participating in a project does not imply leadership.',
  })
})

test('structured exclusions are normalized without invalidating an evidence report', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'answerable', query_kind: 'general',
    sourced_facts: [{ fact: 'Supported.', source_memory_id: 'm1', evidence_quote: 'supported', confidence: 1 }],
    entity_ledger: [], event_ledger: [], pending_action_ledger: [], timeline: [], conflicts: [],
    exclusions: [{ fact: 'Project completion does not prove leadership.', source_memory_id: 'm1' }],
    missing_information: [],
  }))

  assert.equal(parsed.valid, true, parsed.errors.join('\n'))
  assert.deepEqual(parsed.report?.exclusions, ['Project completion does not prove leadership.'])
})

test('temporal conflict decision uses the interval between two sourced events', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'ambiguous', query_kind: 'temporal',
    sourced_facts: [{ fact: 'Two separate events.', source_memory_id: 'm1', evidence_quote: 'separate', confidence: 1 }],
    entity_ledger: [],
    event_ledger: [
      datedEvent('class', 'attend', 'baking class', '2022/03/20'),
      datedEvent('cake', 'make', 'birthday cake', '2022/04/10'),
    ],
    pending_action_ledger: [], timeline: [],
    conflicts: ['The query conflates two separate events that happened apart.'],
    exclusions: [], missing_information: [],
  }))

  assert.deepEqual(deriveEvidenceDecision(
    "How many days ago did I attend a baking class when I made my friend's cake?",
    parsed.report,
  ), {
    kind: 'temporal_interval_days',
    count: 21,
    event_ids: ['class', 'cake'],
    explanation: 'The query combines two separately sourced events, so the supported interval is the difference between their event dates.',
  })
})

test('temporal interval accepts an explicit separation recorded as an exclusion', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'ambiguous', query_kind: 'temporal',
    sourced_facts: [{ fact: 'Two separately dated events.', source_memory_id: 'm1', evidence_quote: 'separate dates', confidence: 1 }],
    entity_ledger: [],
    event_ledger: [
      datedEvent('class', 'attend', 'baking class', '2022/03/20'),
      datedEvent('cake', 'make', 'birthday cake', '2022/04/10'),
    ],
    pending_action_ledger: [], timeline: [], conflicts: [],
    exclusions: ['No evidence links the birthday cake to the baking class; they are separate events on different dates.'],
    missing_information: [],
  }))

  assert.equal(deriveEvidenceDecision(
    "How many days ago did I attend a baking class when I made my friend's cake?",
    parsed.report,
  )?.count, 21)
})

test('last-month acquisition decision counts distinct completed event entities', () => {
  const parsed = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'ambiguous', query_kind: 'multi_session',
    sourced_facts: [{ fact: 'Three plants acquired.', source_memory_id: 'm1', evidence_quote: 'got plants', confidence: 1 }],
    entity_ledger: [],
    event_ledger: [
      acquisitionEvent('peace', 'peace lily'),
      acquisitionEvent('succulent', 'succulent'),
      acquisitionEvent('snake', 'snake plant'),
    ],
    pending_action_ledger: [], timeline: [], conflicts: [], exclusions: [], missing_information: [],
  }))

  assert.deepEqual(deriveEvidenceDecision('How many plants did I acquire in the last month?', parsed.report), {
    kind: 'event_entity_count',
    count: 3,
    event_ids: ['peace', 'succulent', 'snake'],
    explanation: 'Counted distinct completed acquisition events represented in the sourced event ledger.',
  })
})

test('completed buy and cancel questions do not trigger the pending-action guard', () => {
  const report = parseEvidenceReport(JSON.stringify({
    schema_version: '1.0', answerability: 'answerable', query_kind: 'temporal',
    sourced_facts: [{ fact: 'Completed actions.', source_memory_id: 'm1', evidence_quote: 'bought and cancelled', confidence: 1 }],
    entity_ledger: [], event_ledger: [], pending_action_ledger: [], timeline: [],
    conflicts: [], exclusions: [], missing_information: [],
  })).report

  assert.equal(deriveEvidenceDecision('How many days ago did I buy a smoker?', report), null)
  assert.equal(deriveEvidenceDecision(
    'How many days passed between when I cancelled a subscription and bought groceries?',
    report,
  ), null)
})

function event(id: string, action: string, entityId: string, object: string) {
  return {
    id,
    type: 'pending_action',
    action,
    entity_id: entityId,
    object,
    status: 'pending',
    source_memory_id: 'memory-zara',
    source_ref: 'zara-session',
    evidence_quote: object,
    confidence: 1,
  }
}

function action(id: string, action: string, entityId: string, object: string) {
  return { id, action, entity_id: entityId, object, status: 'pending', source_event_id: id }
}

function projectEvent(
  id: string,
  entityId: string,
  sourceRef: string,
  quote: string,
  status: 'pending' | 'completed',
) {
  return {
    id,
    type: 'project_leadership',
    action: 'lead',
    entity_id: entityId,
    object: entityId,
    status,
    source_memory_id: `memory-${sourceRef}`,
    source_ref: sourceRef,
    evidence_quote: quote,
    confidence: 1,
  }
}

function datedEvent(id: string, action: string, object: string, eventTime: string) {
  return {
    id, type: action, action, object, status: 'completed', event_time: eventTime,
    source_memory_id: `memory-${id}`, evidence_quote: object, confidence: 1,
  }
}

function acquisitionEvent(id: string, object: string) {
  return {
    id, type: 'acquisition', action: 'pickup', entity_id: id, object, status: 'completed',
    event_time: '2023/05/01', source_memory_id: `memory-${id}`, evidence_quote: object, confidence: 1,
  }
}
