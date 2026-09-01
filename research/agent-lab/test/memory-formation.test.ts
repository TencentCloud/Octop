import assert from 'node:assert/strict'
import { mkdtemp } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { parseEvidenceResult } from '../src/memory/evidence-result.js'
import { searchMemoryCatalog } from '../src/memory/memory-catalog.js'
import { formConversationSession } from '../src/memory/memory-formation.js'
import { FileMemoryStore } from '../src/memory/store.js'

test('memory formation preserves immutable raw evidence and sourced derived layers', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-formation-'))
  const store = new FileMemoryStore(root)
  const formed = await formConversationSession(store, {
    sessionId: 'festival-session',
    sourceDate: '2023-05-20',
    turns: [
      { role: 'user', content: 'I attended the Austin Film Festival.' },
      { role: 'assistant', content: 'That sounds exciting.' },
      { role: 'user', content: 'Later I joined a Q&A at the Seattle International Film Festival.' },
    ],
    tags: ['test'],
  })

  assert.equal(formed.raw.kind, 'evidence')
  assert.equal(formed.frontmatter.kind, 'topic')
  assert.equal(formed.events.length, 3)
  assert.equal(formed.events.every(event => event.kind === 'event'), true)
  assert.equal(formed.events.every(event => event.source_refs.includes(formed.raw.id)), true)
  assert.equal(formed.events.every(event => event.relations.some(relation =>
    relation.type === 'derived_from' && relation.target === formed.raw.id)), true)
  assert.equal(formed.frontmatter.source_refs.includes(formed.raw.id), true)
  await assert.rejects(
    store.update(formed.raw.id, { summary: 'changed', source_ref: 'test-update' }),
    /Evidence memories are immutable/,
  )
})

test('memory catalog finds a relevant event late in a session without exposing raw content', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-catalog-'))
  const store = new FileMemoryStore(root)
  const formed = await formConversationSession(store, {
    sessionId: 'festival-session',
    sourceDate: '2023-05-20',
    turns: [
      { role: 'user', content: 'I attended the Austin Film Festival.' },
      { role: 'assistant', content: 'That sounds exciting.' },
      { role: 'user', content: 'Later I joined a Q&A at the Seattle International Film Festival.' },
    ],
  })

  const catalog = await searchMemoryCatalog(store, 'Which film festivals did I attend?', {
    maxSources: 4,
    maxEventsPerSource: 4,
    maxChars: 4_000,
  })

  assert.equal(catalog.purpose, 'navigation_only')
  assert.equal(catalog.cards.length, 1)
  assert.equal(catalog.cards[0]?.event_count_hint, 3)
  assert.equal(catalog.cards[0]?.raw_memory_id, formed.raw.id)
  assert.equal(catalog.cards[0]?.matched_events.some(event => /Seattle International/.test(event.summary)), true)
  assert.equal(JSON.stringify(catalog).includes(formed.raw.content), false)
})

test('structured evidence result requires provenance for every candidate', () => {
  const valid = parseEvidenceResult(JSON.stringify({
    schema_version: '1.0',
    task: 'Enumerate festival events.',
    candidates: [{
      id: 'seattle-festival',
      claim: 'The user joined a Q&A at the Seattle International Film Festival.',
      decision: 'include',
      source_refs: ['festival-session#turn-2'],
      memory_ids: ['event-memory-2'],
      source_date: '2023-05-20',
    }],
    covered_memory_ids: ['event-memory-2'],
    covered_source_refs: ['festival-session'],
    unexplored_source_refs: [],
    conflicts: [],
    missing_information: [],
    coverage_status: 'complete',
  }))
  assert.equal(valid.valid, true)

  const unsupported = parseEvidenceResult(JSON.stringify({
    schema_version: '1.0',
    task: 'Enumerate festival events.',
    candidates: [{
      id: 'unsupported',
      claim: 'Unsupported claim.',
      decision: 'include',
      source_refs: [],
      memory_ids: [],
    }],
    covered_memory_ids: [],
    covered_source_refs: [],
    unexplored_source_refs: ['unknown-session'],
    conflicts: [],
    missing_information: [],
    coverage_status: 'complete',
  }))
  assert.equal(unsupported.valid, false)
  assert.equal(unsupported.errors.some(error => /requires at least one source_ref/.test(error)), true)
  assert.equal(unsupported.errors.some(error => /complete coverage/.test(error)), true)
})

test('structured evidence schema 1.1 derives provenance and coverage from a compact decision', () => {
  const parsed = parseEvidenceResult(JSON.stringify({
    schema_version: '1.1',
    task: 'Resolve the latest supported state.',
    candidates: [{
      id: 'latest-state',
      claim: 'The latest sourced state is active.',
      decision: 'include',
      source_refs: ['session-a#turn-2'],
      memory_ids: ['event-a'],
      source_date: '2025-01-03',
    }],
    coverage: {
      inspected_source_refs: ['session-a'],
      unresolved_source_refs: [],
      stop_reason: 'assigned_scope_exhausted',
    },
  }))

  assert.equal(parsed.valid, true)
  assert.equal(parsed.result?.coverage_status, 'complete')
  assert.deepEqual(parsed.result?.covered_memory_ids, ['event-a'])
  assert.deepEqual(parsed.result?.covered_source_refs, ['session-a#turn-2', 'session-a'])
})

test('structured evidence schema 1.1 rejects an exhaustive stop with unresolved sources', () => {
  const parsed = parseEvidenceResult(JSON.stringify({
    schema_version: '1.1',
    task: 'Audit all assigned sources.',
    candidates: [],
    coverage: {
      inspected_source_refs: ['session-a'],
      unresolved_source_refs: ['session-b'],
      stop_reason: 'assigned_scope_exhausted',
    },
  }))

  assert.equal(parsed.valid, false)
  assert.equal(parsed.factValid, true)
  assert.equal(parsed.coverageComplete, false)
  assert.equal(parsed.factErrors.length, 0)
  assert.equal(parsed.result?.coverage_status, 'incomplete')
  assert.equal(parsed.errors.some(error => /exhaustive coverage stop_reason/.test(error)), true)
})

test('structured evidence result recovers complete sourced candidates from truncated JSON', () => {
  const parsed = parseEvidenceResult([
    '{"schema_version":"1.0","task":"Find properties","candidates":[',
    '{"id":"oakwood","claim":"Viewed Oakwood bungalow","decision":"include","source_refs":["session-1#turn-0"],"memory_ids":["event-1"]},',
    '{"id":"cedar","claim":"Viewed Cedar Creek property","decision":"include","source_refs":["session-2#turn-0"],"memory_ids":["event-2"]},',
    '{"id":"partial","claim":"This candidate is cut off","decision":"include","source_refs":["session-3',
  ].join(''))

  assert.equal(parsed.valid, false)
  assert.equal(parsed.result?.coverage_status, 'uncertain')
  assert.deepEqual(parsed.result?.candidates.map(candidate => candidate.id), ['oakwood', 'cedar'])
  assert.deepEqual(parsed.result?.covered_memory_ids, ['event-1', 'event-2'])
})

test('structured evidence result cannot claim complete coverage with an unread memory tail', () => {
  const parsed = parseEvidenceResult(JSON.stringify({
    schema_version: '1.0',
    task: 'Audit a long source.',
    candidates: [{
      id: 'museum',
      claim: 'The user visited a museum.',
      decision: 'include',
      source_refs: ['museum-session#turn-0'],
      memory_ids: ['museum-memory'],
    }],
    covered_memory_ids: ['museum-memory'],
    covered_source_refs: ['museum-session'],
    unexplored_source_refs: [],
    conflicts: [],
    missing_information: ['Source has remaining unread content (offset 14400 of 15923 chars).'],
    coverage_status: 'complete',
  }))

  assert.equal(parsed.valid, false)
  assert.equal(parsed.factValid, true)
  assert.equal(parsed.coverageComplete, false)
  assert.equal(parsed.result?.coverage_status, 'incomplete')
  assert.equal(parsed.errors.includes('complete coverage cannot contain unread memory windows'), true)
})

test('structured evidence promotes an explicit unresolved obligation over inferred completion', () => {
  const parsed = parseEvidenceResult(JSON.stringify({
    schema_version: '1.0',
    task: 'Count pending store actions.',
    candidates: [{
      id: 'return-old-boots',
      claim: 'User needs to return the old boots to the store.',
      decision: 'uncertain',
      source_refs: ['session#turn-6'],
      memory_ids: ['memory-1'],
      reason: 'Nearby text says the boots were exchanged, so completion was inferred.',
    }],
    covered_memory_ids: ['memory-1'],
    covered_source_refs: ['session'],
    unexplored_source_refs: [],
    conflicts: [],
    missing_information: [],
    coverage_status: 'complete',
  }))

  assert.equal(parsed.valid, true)
  assert.equal(parsed.result?.candidates[0]?.decision, 'include')
})
