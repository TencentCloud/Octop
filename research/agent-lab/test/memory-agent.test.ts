import assert from 'node:assert/strict'
import { access, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createToolResultMessage, createUserMessage } from '../src/core/messages.js'
import { ScriptedModel, assistantWithToolCalls, createToolCall } from '../src/core/mock-model.js'
import { MemoryContextManager } from '../src/memory/context-manager.js'
import { compileEvidenceBundle } from '../src/memory/evidence-bundle.js'
import {
  applyCompileEvidenceAnswerGuard,
  compileCoverageFollowUp,
  createMemoryAgent,
} from '../src/memory/runtime.js'
import { FileMemoryStore } from '../src/memory/store.js'
import { createMemoryTools, selectSourceBalancedHits } from '../src/memory/tools.js'
import type { MemoryHit } from '../src/memory/types.js'

function source(ref: string) {
  return {
    type: 'conversation' as const,
    ref,
    observed_at: '2026-07-11T09:00:00.000Z',
  }
}

test('memory search selection exposes source diversity before repeated hits', () => {
  const hit = (id: string, sourceRef: string, score: number): MemoryHit => ({
    id,
    kind: 'event',
    title: id,
    summary: id,
    tags: ['user'],
    source_ref: sourceRef,
    source_refs: [`${sourceRef}#turn-0`],
    entities: [],
    status: 'active',
    confidence: 1,
    score,
  })
  const selected = selectSourceBalancedHits([
    hit('a1', 'source-a', 1),
    hit('a2', 'source-a', 0.9),
    hit('b1', 'source-b', 0.8),
    hit('c1', 'source-c', 0.7),
  ], 3)

  assert.deepEqual(selected.map(item => item.id), ['a1', 'b1', 'c1'])
})

test('compile coverage follow-up exposes only concrete unresolved source refs', () => {
  const incomplete = compileCoverageFollowUp([createToolResultMessage({
    toolCallId: 'compile-1',
    toolName: 'CompileEvidence',
    content: JSON.stringify({
      evidence_packet: {
        coverage_status: 'incomplete',
        unexplored_sources: ['source-b', 'source-b'],
      },
      cross_source_coverage: {
        status: 'incomplete',
        unresolved_source_refs: ['source-b', 'source-c'],
      },
    }),
  })])
  assert.deepEqual(incomplete, { sourceRefs: ['source-b', 'source-c'] })

  const complete = compileCoverageFollowUp([createToolResultMessage({
    toolCallId: 'compile-2',
    toolName: 'CompileEvidence',
    content: JSON.stringify({
      evidence_packet: { coverage_status: 'complete', unexplored_sources: [] },
      cross_source_coverage: { status: 'complete', unresolved_source_refs: [] },
    }),
  })])
  assert.equal(complete, null)
})

test('compile answer guard rejects evidence-record counts and preserves parent preference synthesis', () => {
  const runResult = (
    query: string,
    output: string,
    evidencePacket: Record<string, unknown>,
  ): import('../src/core/agent-loop.js').RunAgentLoopResult => ({
    status: 'completed',
    output,
    events: [],
    messages: [
      createUserMessage(query),
      createToolResultMessage({
        toolCallId: 'compile',
        toolName: 'CompileEvidence',
        content: JSON.stringify({ evidence_packet: evidencePacket }),
      }),
      { role: 'assistant', content: output },
    ],
  })

  const scalar = runResult('How many postcards have I added?', '25 postcards.', {
    coverage_status: 'incomplete',
    count_contract: 'deterministic',
    included_count: 4,
    included: Array.from({ length: 4 }, (_, index) => ({ id: `evidence-${index}` })),
    answer_contract: {
      operation: 'count',
      final_answer: '25 postcards.',
      projection_status: 'review',
    },
  })
  assert.equal(applyCompileEvidenceAnswerGuard(scalar, 'How many postcards have I added?').output, '25 postcards.')

  const cardinality = runResult('How many projects did I lead?', 'I found two projects.', {
    coverage_status: 'complete',
    count_contract: 'deterministic',
    included_count: 3,
    included: Array.from({ length: 3 }, (_, index) => ({ id: `project-${index}` })),
    answer_contract: {
      operation: 'count',
      final_answer: '3 projects.',
      projection_status: 'committed',
    },
  })
  const corrected = applyCompileEvidenceAnswerGuard(cardinality, 'How many projects did I lead?')
  assert.equal(corrected.output, '3 projects.')
  assert.equal(corrected.events.some(event => event.type === 'answer_guard_applied'), true)

  const preference = runResult('What should I use to navigate Tokyo?', 'Use your Suica card with TripIt.', {
    coverage_status: 'complete',
    answer_contract: {
      operation: 'preference',
      final_answer: 'Suica and TripIt are supported personalization anchors.',
      projection_status: 'committed',
    },
  })
  assert.equal(
    applyCompileEvidenceAnswerGuard(preference, 'What should I use to navigate Tokyo?').output,
    'Use your Suica card with TripIt.',
  )
})

test('orchestrator ledger performs one bounded coverage repair before final synthesis', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-coverage-repair-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 12_000, preserveRecentChars: 8_000, summaryMaxChars: 2_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)

  let parentTurn = 0
  let childRuns = 0
  let compilerRuns = 0
  let sawRepairInstruction = false
  const model = {
    async next(
      messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      const isCompiler = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated evidence compiler'))
      if (isCompiler) {
        compilerRuns++
        const repaired = compilerRuns === 2
        return { role: 'assistant' as const, content: JSON.stringify({
          answerability: 'answerable',
          derived_count: null,
          derived_answer: repaired ? 'Both sources support the final answer.' : 'Source A supports a preliminary answer.',
          included: repaired
            ? [
                { id: 'fact-a', claim: 'Fact A.', result_ids: ['r-a'], source_refs: ['source-a'] },
                { id: 'fact-b', claim: 'Fact B.', result_ids: ['r-b'], source_refs: ['source-b'] },
              ]
            : [{ id: 'fact-a', claim: 'Fact A.', result_ids: ['r-a'], source_refs: ['source-a'] }],
          excluded: [],
          coverage_status: repaired ? 'complete' : 'incomplete',
          unexplored_sources: repaired ? [] : ['source-b#turn-4'],
          conflicts: [],
          missing_information: repaired ? [] : ['source-b has not been inspected'],
          answer_contract: {
            operation: 'fact_lookup',
            final_answer: repaired ? 'Final supported answer.' : 'Preliminary answer.',
            included_ids: repaired ? ['fact-a', 'fact-b'] : ['fact-a'],
            excluded_ids: [],
          },
        }) }
      }

      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated memory evidence subagent'))
      if (isChild) {
        childRuns++
        const repaired = childRuns === 2
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.1',
          task: repaired ? 'Repair source-b coverage.' : 'Inspect initial evidence.',
          candidates: [{
            id: repaired ? 'fact-b' : 'fact-a',
            claim: repaired ? 'Fact B.' : 'Fact A.',
            decision: 'include',
            source_refs: [repaired ? 'source-b#turn-4' : 'source-a'],
            memory_ids: [repaired ? 'memory-b' : 'memory-a'],
          }],
          coverage: {
            inspected_source_refs: [repaired ? 'source-b#turn-4' : 'source-a'],
            unresolved_source_refs: repaired ? [] : ['source-b#turn-4'],
            stop_reason: repaired ? 'assigned_scope_exhausted' : 'unresolved_sources',
          },
          conflicts: [],
            missing_information: repaired ? [] : ['source-b#turn-4 remains unread'],
        }) }
      }

      parentTurn++
      if (parentTurn === 1 || parentTurn === 4) {
        sawRepairInstruction ||= messages.some(message =>
          message.role === 'system' && message.content.includes('bounded coverage repair'))
        return assistantWithToolCalls('', [createToolCall(`fork-${parentTurn}`, 'ForkSubagent', {
          description: parentTurn === 1 ? 'Inspect initial evidence' : 'Repair unresolved source',
          prompt: parentTurn === 1 ? 'Find the supported facts.' : 'Inspect only source-b for missing facts.',
          allowed_tools: ['MemorySearch', 'MemoryRead', 'MemoryEvidenceBundle'],
          ...(parentTurn === 4 ? { context_refs: ['source-b#turn-4'] } : {}),
        })])
      }
      if (parentTurn === 2 || parentTurn === 5) {
        const resultIds = messages.flatMap(message => {
          if (message.role !== 'tool' || message.tool_name !== 'ForkSubagent') return []
          const parsed = JSON.parse(message.content) as { result_id?: string }
          return parsed.result_id ? [parsed.result_id] : []
        })
        return assistantWithToolCalls('', [createToolCall(`compile-${parentTurn}`, 'CompileEvidence', {
          objective: 'Compile all supported facts for the original question.',
          result_ids: [resultIds.at(-1)],
        })])
      }
      return { role: 'assistant' as const, content: parentTurn === 3 ? 'Preliminary parent answer.' : 'Final supported answer.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('What is the final supported answer?')],
    10,
    undefined,
    {
      parentMode: 'orchestrator-ledger',
      structuredEvidenceResults: true,
      forkSubagentMaxTurns: 4,
      reserveFinalAnswerTurn: true,
    },
  )

  assert.equal(result.output, 'Final supported answer.')
  assert.equal(sawRepairInstruction, true)
  assert.equal(childRuns, 2)
  assert.equal(compilerRuns, 2)
  assert.equal((await agent.results.list()).length, 2)
})

test('v51 runtime profile preserves schema 1.0 flow without automatic coverage repair', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-v51-profile-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 12_000, preserveRecentChars: 8_000, summaryMaxChars: 2_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)

  let parentTurn = 0
  let childRuns = 0
  let compilerRuns = 0
  let sawRepairInstruction = false
  let compilerSawCurrentFields = false
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isCompiler = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated evidence compiler'))
      if (isCompiler) {
        compilerRuns++
        compilerSawCurrentFields ||= messages.some(message =>
          message.content.includes('cross_source_coverage') || message.content.includes('fact_packet_valid'))
        return { role: 'assistant' as const, content: JSON.stringify({
          answerability: 'partial',
          derived_count: null,
          derived_answer: 'Source A supports a preliminary answer.',
          included: [{ id: 'fact-a', claim: 'Fact A.', result_ids: ['r-a'], source_refs: ['source-a'] }],
          excluded: [],
          coverage_status: 'incomplete',
          unexplored_sources: ['source-b'],
          conflicts: [],
          missing_information: ['source-b has not been inspected'],
        }) }
      }

      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated memory evidence subagent'))
      if (isChild) {
        childRuns++
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0',
          task: 'Inspect initial evidence.',
          candidates: [{
            id: 'fact-a',
            claim: 'Fact A.',
            decision: 'include',
            source_refs: ['source-a'],
            memory_ids: ['memory-a'],
          }],
          covered_memory_ids: ['memory-a'],
          covered_source_refs: ['source-a'],
          unexplored_source_refs: ['source-b'],
          coverage_status: 'incomplete',
          conflicts: [],
          missing_information: ['source-b remains unread'],
        }) }
      }

      parentTurn++
      sawRepairInstruction ||= messages.some(message =>
        message.role === 'system' && message.content.includes('bounded coverage repair'))
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('fork-v51', 'ForkSubagent', {
          description: 'Inspect initial evidence',
          prompt: 'Find the supported facts.',
          allowed_tools: ['MemorySearch', 'MemoryRead', 'MemoryEvidenceBundle'],
        })])
      }
      if (parentTurn === 2) {
        const resultId = messages.flatMap(message => {
          if (message.role !== 'tool' || message.tool_name !== 'ForkSubagent') return []
          const parsed = JSON.parse(message.content) as { result_id?: string }
          return parsed.result_id ? [parsed.result_id] : []
        }).at(-1)
        return assistantWithToolCalls('', [createToolCall('compile-v51', 'CompileEvidence', {
          objective: 'Compile supported facts for the original question.',
          result_ids: [resultId],
        })])
      }
      return { role: 'assistant' as const, content: 'Preliminary answer from the available evidence.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('What is the supported answer?')],
    10,
    undefined,
    {
      parentMode: 'orchestrator-ledger',
      structuredEvidenceResults: true,
      runtimeProfile: 'v51',
      forkSubagentMaxTurns: 4,
      reserveFinalAnswerTurn: true,
    },
  )

  assert.equal(result.output, 'Preliminary answer from the available evidence.')
  assert.equal(sawRepairInstruction, false)
  assert.equal(compilerSawCurrentFields, false)
  assert.equal(childRuns, 1)
  assert.equal(compilerRuns, 1)
  assert.equal((await agent.results.list()).length, 1)
})

test('memory store supports sourced CRUD, revisions, search, and soft delete', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-store-'))
  const store = new FileMemoryStore(root)
  const created = await store.create({
    kind: 'semantic',
    title: 'Reader failure conclusion',
    summary: 'Retrieval finds evidence but the reader misses temporal relations.',
    content: 'recall_all@50 is 1.0 while temporal judge score is 0.40.',
    tags: ['reader', 'temporal'],
    source: source('experiment-500'),
    temporal: { event_time: '2026-07-10' },
    confidence: 0.95,
  })

  const hits = await store.search({ query: 'reader temporal evidence' })
  assert.equal(hits[0]?.id, created.id)
  assert.equal(hits[0]?.source_ref, 'experiment-500')

  const duplicate = await store.create({
    kind: 'semantic',
    title: ' Reader failure conclusion ',
    summary: 'A duplicate write attempt.',
    content: ' recall_all@50 is 1.0 while temporal judge score is 0.40. ',
    tags: ['duplicate'],
    source: source('experiment-500'),
  })
  assert.equal(duplicate.id, created.id)

  const updated = await store.update(created.id, {
    summary: 'Reader failure is strongest on temporal questions.',
    expected_revision: 1,
    source_ref: 'experiment-review',
  })
  assert.equal(updated.revision, 2)
  await assert.rejects(
    store.update(created.id, {
      summary: 'stale write',
      expected_revision: 1,
      source_ref: 'stale-agent',
    }),
    /Revision conflict/,
  )

  const deleted = await store.delete(created.id, 'cleanup-test')
  assert.equal(deleted.status, 'deleted')
  assert.equal(await store.read(created.id), null)
  assert.equal((await store.read(created.id, true))?.revision, 3)
  assert.equal((await store.search({ query: 'reader' })).length, 0)

  const auditLines = (await readFile(path.join(root, 'audit.jsonl'), 'utf8')).trim().split('\n')
  assert.deepEqual(auditLines.map(line => JSON.parse(line).operation), ['create', 'update', 'delete'])
})

test('MemoryRead progressively exposes long raw memory without losing provenance', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-read-window-'))
  const store = new FileMemoryStore(root)
  const lateFact = 'user: The Museum of Contemporary Art visit happened second.'
  const created = await store.create({
    kind: 'episodic',
    title: 'Long museum conversation',
    summary: 'A long source whose relevant fact occurs near the end.',
    content: `${'user: Earlier unrelated discussion.\nassistant: Acknowledged.\n'.repeat(80)}${lateFact}`,
    source: source('museum-session'),
    source_refs: ['museum-turns'],
    temporal: { event_time: '2023-01-22' },
  })
  const read = createMemoryTools(store).find(tool => tool.name === 'MemoryRead')
  assert.ok(read)

  const first = await read.call({ id: created.id, max_chars: 800 }, {} as never) as {
    id: string
    source: { ref: string }
    source_refs: string[]
    content: string
    read_window: { next_offset: number | null; has_more: boolean; total_chars: number }
  }
  assert.equal(first.id, created.id)
  assert.equal(first.source.ref, 'museum-session')
  assert.deepEqual(first.source_refs, ['museum-turns', 'museum-session'])
  assert.equal(first.read_window.has_more, true)
  assert.equal(first.content.includes(lateFact), false)

  let page = first
  let reconstructed = first.content
  while (page.read_window.has_more) {
    assert.notEqual(page.read_window.next_offset, null)
    page = await read.call({
      id: created.id,
      offset: page.read_window.next_offset as number,
      max_chars: 800,
    }, {} as never) as typeof first
    reconstructed += page.content
  }

  assert.equal(reconstructed, created.content)
  assert.equal(page.content.includes(lateFact), true)
  assert.equal(page.read_window.total_chars, created.content.length)
  assert.equal(JSON.stringify(first).length < 4_000, true)
})

test('memory v2 keeps evidence immutable and validates event and state provenance', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-v2-'))
  const store = new FileMemoryStore(root)
  const evidence = await store.create({
    kind: 'evidence',
    title: 'User dated claim',
    summary: 'The user reported a museum visit on January 8.',
    content: 'I visited MoMA on January 8.',
    source: source('session-evidence'),
    entities: ['user', 'MoMA'],
    source_refs: ['turn-17'],
  })

  assert.equal(evidence.schema_version, '2.0')
  assert.deepEqual(evidence.source_refs, ['turn-17', 'session-evidence'])
  await access(path.join(root, 'evidence', `${evidence.id}.json`))
  await assert.rejects(
    store.update(evidence.id, { summary: 'changed', source_ref: 'bad-update' }),
    /immutable/,
  )
  await assert.rejects(store.delete(evidence.id, 'bad-delete'), /immutable/)
  await assert.rejects(store.create({
    kind: 'event',
    title: 'Undated event',
    summary: 'Missing time.',
    content: 'An event happened.',
    source: source('event-session'),
  }), /require temporal/)
  await assert.rejects(store.create({
    kind: 'state',
    title: 'Unsupported state',
    summary: 'No provenance.',
    content: 'The user currently prefers museums.',
    source: source('state-session'),
  }), /require source_refs/)

  const event = await store.create({
    kind: 'event',
    title: 'MoMA visit',
    summary: 'The user visited MoMA.',
    content: 'Visit event grounded in the original claim.',
    source: source('event-session'),
    source_refs: [evidence.id],
    entities: ['user', 'MoMA'],
    temporal: { event_time: '2026-01-08' },
    event_status: 'completed',
    relations: [{ type: 'derived_from', target: evidence.id }],
  })
  await access(path.join(root, 'events', `${event.id}.json`))
  const hit = (await store.search({ query: 'MoMA visit' })).find(item => item.id === event.id)
  assert.deepEqual(hit?.entities, ['user', 'MoMA'])
  assert.equal(hit?.event_status, 'completed')
})

test('enabled memory curator runs in isolation with derived-only deletion permissions', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-curator-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    curator: { enabled: true, maxTurns: 3, maxContextChars: 8_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  let parentTurns = 0
  let curatorTools: string[] = []
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isCurator = messages.some(
        message => message.role === 'system' && message.content.includes('Memory Curator Subagent'),
      )
      if (!isCurator) {
        parentTurns++
        return { role: 'assistant' as const, content: 'Noted that you visited MoMA on January 8.' }
      }

      curatorTools = context.tools.map(tool => tool.name)
      const existingResult = messages.find(
        message => message.role === 'tool' && message.tool_name === 'MemoryCreate',
      )
      if (!existingResult) {
        return assistantWithToolCalls('store immutable source evidence', [
          createToolCall('curate_1', 'MemoryCreate', {
            kind: 'evidence',
            title: 'MoMA visit claim',
            summary: 'The user said they visited MoMA on January 8.',
            content: 'I visited MoMA on January 8.',
            source: source('curator-session'),
            source_refs: ['curator-turn-1'],
            entities: ['user', 'MoMA'],
          }),
        ])
      }
      return {
        role: 'assistant' as const,
        content: JSON.stringify({ action: 'write', reason: 'Durable dated user claim.', memory_ids: [] }),
      }
    },
  }

  const result = await agent.run(model, [createUserMessage('I visited MoMA on January 8.')])

  assert.equal(parentTurns, 1)
  assert.deepEqual(curatorTools, [
    'MemorySearch',
    'MemoryRead',
    'MemoryCreate',
    'MemoryUpdate',
    'MemoryDeleteDerived',
  ])
  assert.equal(result.events.some(event => event.type === 'subagent_start' && event.kind === 'memory_curator'), true)
  assert.equal(result.events.some(event => event.type === 'subagent_end' && event.kind === 'memory_curator'), true)
  assert.equal((await agent.store.search({ query: 'MoMA January' }))[0]?.kind, 'evidence')
})

test('context manager injects source-diverse, temporal memory packets without mutating history', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-context-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic',
    title: 'Temporal experiment result',
    summary: 'Temporal reader score reached 0.40.',
    content: 'The evidence was retrieved, but relative dates were interpreted incorrectly.',
    source: source('session-a'),
    temporal: { event_time: '2026-07-10' },
  })
  await store.create({
    kind: 'semantic',
    title: 'Temporal reader lesson',
    summary: 'Preserve event anchors and inclusive date boundaries.',
    content: 'Readers must expose event_time, valid_from, and valid_to.',
    source: source('session-b'),
  })

  const manager = new MemoryContextManager(store, { maxItems: 2, maxChars: 4000, minScore: 0.01 })
  const original = [createUserMessage('What did we learn about the temporal reader?')]
  const prepared = await manager.prepare(original, 1)

  assert.equal(original.length, 1)
  assert.equal(prepared.messages[0]?.role, 'system')
  assert.match(prepared.messages[0]?.content ?? '', /<memory_context>/)
  assert.match(prepared.messages[0]?.content ?? '', /session-a/)
  assert.match(prepared.messages[0]?.content ?? '', /session-b/)
  assert.match(prepared.messages[0]?.content ?? '', /event_time=2026-07-10/)
})

test('context manager does not duplicate full memory after a valid evidence reader report', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-context-reader-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic', title: 'Relevant record', summary: 'A relevant fact.', content: 'Full source text.',
    source: source('source-one'),
  })
  const manager = new MemoryContextManager(store, { maxItems: 4, maxChars: 4_000, minScore: 0.01 })
  const messages = [
    createUserMessage('What is the relevant fact?'),
    createToolResultMessage({
      toolCallId: 'reader-1',
      toolName: 'ForkEvidenceReader',
      content: JSON.stringify({ report_valid: true, report: { sourced_facts: [] } }),
    }),
  ]
  const prepared = await manager.prepare(messages, 2)

  assert.equal(prepared.messages.some(message => message.content.includes('<memory_context>')), false)
  assert.equal(prepared.metadata?.memoryInjectionSkipped, 'evidence_reader_result_present')
})

test('context manager preserves memory tool history instead of reinjecting the same packet', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-context-tool-result-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic', title: 'Relevant record', summary: 'A relevant fact.', content: 'Full source text.',
    source: source('source-one'),
  })
  const manager = new MemoryContextManager(store, { maxItems: 4, maxChars: 4_000, minScore: 0.01 })
  const messages = [
    createUserMessage('What is the relevant fact?'),
    createToolResultMessage({
      toolCallId: 'search-1',
      toolName: 'MemorySearch',
      content: JSON.stringify([{ id: 'memory-1', summary: 'A relevant fact.' }]),
    }),
  ]
  const prepared = await manager.prepare(messages, 2)

  assert.deepEqual(prepared.messages, messages)
  assert.equal(prepared.messages.some(message => message.content.includes('<memory_context>')), false)
  assert.equal(prepared.metadata?.memoryInjectionSkipped, 'memory_tool_result_present')
})

test('evidence bundle groups sources, preserves speaker roles, and reports coverage gaps', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'evidence-bundle-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic',
    title: 'Store errands',
    summary: 'The user needs to return boots and pick up a blazer.',
    content: 'user: I need to return boots to Zara.\nassistant: Noted.\nuser: I still need to pick up my navy blazer.',
    source: source('errands-session'),
    temporal: { event_time: '2026-02-15' },
  })
  await store.create({
    kind: 'episodic',
    title: 'Unrelated farm discussion',
    summary: 'The user asked about a store selling farm fencing.',
    content: 'user: Which store sells fencing for goats?\nassistant: Try a farm supplier.',
    source: source('farm-session'),
  })

  const bundle = await compileEvidenceBundle(
    store,
    'How many clothing items do I need to pick up or return from a store?',
    { maxSources: 4, maxChars: 6_000 },
  )

  assert.equal(bundle.status, 'evidence_found')
  assert.equal(bundle.source_clusters[0]?.source_ref, 'errands-session')
  const evidenceText = bundle.source_clusters[0]?.snippets.map(item => item.text).join(' ') ?? ''
  assert.match(evidenceText, /boots/i)
  assert.match(evidenceText, /blazer/i)
  assert.equal(bundle.covered_facets.includes('return'), true)
  assert.equal(bundle.covered_facets.includes('pick'), true)
  assert.equal(bundle.covered_facets.includes('clothing'), true)
  assert.equal(bundle.stats.chars <= 6_000, true)
})

test('evidence bundle exposes relevant assistant-authored memory with role attribution', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'evidence-assistant-role-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic',
    title: 'Shift rotation',
    summary: 'The user requested a Sunday shift rotation for Admon.',
    content: [
      'user: Please assign Admon in the Sunday rotation.',
      'assistant: On Sunday, Admon is assigned to the 8 am - 4 pm Day Shift.',
    ].join('\n'),
    source: source('rotation-session'),
  })

  const bundle = await compileEvidenceBundle(store, 'What was the Sunday rotation for Admon?', {
    maxSources: 4,
    maxChars: 6_000,
    preferredRole: 'assistant',
  })
  const snippets = bundle.source_clusters[0]?.snippets ?? []

  assert.equal(snippets.some(snippet => snippet.role === 'assistant' && /8 am - 4 pm/i.test(snippet.text)), true)
  assert.equal(snippets.every(snippet => snippet.role === 'assistant'), true)
})

test('evidence bundle expands bounded answer-source families and lexical aliases', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'evidence-family-'))
  const store = new FileMemoryStore(root)
  await store.create({
    kind: 'episodic', title: 'Dermatology visit', summary: 'Follow-up appointment with a dermatologist.',
    content: 'user: I just got back from an appointment with my dermatologist.',
    source: source('answer_health_3'),
  })
  await store.create({
    kind: 'episodic', title: 'Primary care', summary: 'A physician prescribed antibiotics.',
    content: 'user: My primary care physician prescribed antibiotics for a UTI.',
    source: source('answer_health_1'),
  })
  await store.create({
    kind: 'episodic', title: 'Sinus diagnosis', summary: 'An ENT specialist diagnosed sinusitis.',
    content: 'user: An ENT specialist diagnosed me with chronic sinusitis.',
    source: source('answer_health_2'),
  })

  const bundle = await compileEvidenceBundle(store, 'How many different doctors did I visit?', {
    maxSources: 6,
    maxChars: 6_000,
  })

  assert.deepEqual(
    bundle.source_clusters.map(cluster => cluster.source_ref).sort(),
    ['answer_health_1', 'answer_health_2', 'answer_health_3'],
  )
  assert.equal(bundle.covered_facets.includes('doctor'), true)
  assert.equal(bundle.covered_facets.includes('visit'), true)
})

test('memory agent feeds a newly created memory into the next model turn', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-agent-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4000, minScore: 0.01 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)

  const model = new ScriptedModel([
    assistantWithToolCalls('I will retain the experiment result.', [
      createToolCall('memory_1', 'MemoryCreate', {
        kind: 'semantic',
        title: 'Temporal reader result',
        summary: 'Temporal judge score is 0.40 despite perfect recall.',
        content: 'recall_all@50=1.0, judge=0.40; improve date-chain reading.',
        tags: ['temporal', 'reader'],
        source: source('episode-eval'),
        temporal: { event_time: '2026-07-11' },
        confidence: 1,
      }),
    ]),
    messages => {
      const injected = messages.find(message => message.role === 'system')
      return {
        role: 'assistant',
        content: injected?.content.includes('judge=0.40')
          ? 'I recovered the sourced temporal result.'
          : 'Memory was not injected.',
      }
    },
  ])

  const result = await agent.run(model, [createUserMessage('Remember the temporal reader result')])
  assert.equal(result.status, 'completed')
  assert.equal(result.output, 'I recovered the sourced temporal result.')
  assert.equal(result.messages.filter(message => message.role === 'system').length, 0)
})

test('memory agent forks an isolated read-only evidence reader subagent', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-subagent-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  await agent.store.create({
    kind: 'episodic',
    title: 'Museum visits',
    summary: 'The user visited MoMA and then the Met.',
    content: 'MoMA: January 8. Met: January 15.',
    source: source('museum-session'),
    temporal: { event_time: '2026-01-15' },
  })

  let parentTurns = 0
  let childToolNames: string[] = []
  let childSawBundle = false
  let childSawInjectedMemoryPacket = false
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isChild = messages.some(message => message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
      if (isChild) {
        childToolNames = context.tools.map(tool => tool.name)
        childSawBundle = messages.some(message => message.content.includes('<initial_evidence_bundle>'))
        childSawInjectedMemoryPacket = messages.some(message => message.content.includes('<memory_context>'))
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0',
          answerability: 'answerable',
          query_kind: 'temporal',
          sourced_facts: [{ fact: 'The visits were 7 days apart.', source_memory_id: 'museum-memory', source_ref: 'museum-session', evidence_quote: 'January 8 and January 15', confidence: 1 }],
          entity_ledger: [],
          event_ledger: [],
          pending_action_ledger: [],
          timeline: [],
          conflicts: [],
          exclusions: [],
          missing_information: [],
        }) }
      }
      parentTurns++
      if (parentTurns === 1) {
        return assistantWithToolCalls('delegating evidence reading', [
          createToolCall('fork_1', 'ForkEvidenceReader', {
            query: 'How many days passed between the museum visits?',
            objective: 'Extract both dated event anchors and calculate no final answer.',
          }),
        ])
      }
      const report = messages.find(message => message.role === 'tool' && message.tool_name === 'ForkEvidenceReader')
      return { role: 'assistant' as const, content: `parent used report: ${report?.content}` }
    },
  }

  const result = await agent.run(model, [createUserMessage('museum duration')])
  assert.deepEqual(childToolNames, ['MemorySearch', 'MemoryRead', 'MemoryEvidenceBundle'])
  assert.equal(childSawBundle, true)
  assert.equal(childSawInjectedMemoryPacket, false)
  assert.equal(result.events.some(event => event.type === 'subagent_start'), true)
  assert.equal(result.events.some(event => event.type === 'subagent_end'), true)
  assert.match(result.output ?? '', /7 days/)
  const sidechains = await agent.sidechains.list()
  assert.equal(sidechains.length, 1)
  assert.equal(sidechains[0]?.kind, 'evidence_reader')
  assert.equal(sidechains[0]?.messages.some(message =>
    message.role === 'system' && message.content.includes('Evidence Reader Subagent')),
  true)
  assert.equal(result.messages.some(message =>
    message.role === 'system' && message.content.includes('Evidence Reader Subagent')),
  false)
})

test('evidence reader compiles a truncated stage-one report from a bounded isolated packet', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-reader-compiler-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  const memory = await agent.store.create({
    kind: 'episodic',
    title: 'Updated attendance',
    summary: 'The user attended five support group sessions.',
    content: 'user: I attended 5 sessions of the bereavement support group.',
    source: source('support-group-session'),
  })

  let compilerSawReaderConversation = false
  let compilerSawSourceDate = false
  let compilerCalls = 0
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isCompiler = messages.some(message =>
        message.role === 'system' && message.content.includes('Evidence Report Compiler Stage 2'))
      if (isCompiler) {
        compilerCalls++
        compilerSawReaderConversation = messages.some(message =>
          message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
        compilerSawSourceDate = messages.some(message =>
          message.role === 'user' && message.content.includes('"source_date"'))
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0', answerability: 'answerable', query_kind: 'state_latest',
          sourced_facts: [{
            fact: 'The user attended five support group sessions.',
            source_memory_id: memory.id,
            source_ref: 'support-group-session',
            evidence_quote: 'I attended 5 sessions of the bereavement support group.',
            confidence: 1,
          }],
          entity_ledger: [], event_ledger: [], pending_action_ledger: [], timeline: [],
          conflicts: [], exclusions: [], missing_information: [],
        }) }
      }
      const isReader = messages.some(message =>
        message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
      if (isReader) return { role: 'assistant' as const, content: '{"schema_version":"1.0","answerability":' }

      return { role: 'assistant' as const, content: 'You attended five sessions.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('How many bereavement support group sessions did I attend?')],
    3,
    undefined,
    { forceEvidenceReader: true, finalAnswerWithoutTools: true },
  )

  assert.equal(result.output, 'You attended five sessions.')
  assert.equal(compilerSawReaderConversation, false)
  assert.equal(compilerSawSourceDate, true)
  assert.equal(compilerCalls, 1)
  const outcomeMessage = result.messages.find(message =>
    message.role === 'tool' && message.tool_name === 'ForkEvidenceReader')
  const parentOutcome = JSON.parse(outcomeMessage?.content ?? '{}') as Record<string, unknown>
  assert.equal(parentOutcome?.report_valid, true)
  assert.equal(parentOutcome?.report_compiled, true)
  assert.equal((parentOutcome?.report_stages as { compiler?: { used?: boolean } })?.compiler?.used, true)
})

test('memory agent can deterministically route high-risk questions through the evidence reader', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-routed-subagent-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)

  let parentCalls = 0
  let parentSawForkResult = false
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isChild = messages.some(message => message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
      if (isChild) {
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0',
          answerability: 'answerable',
          query_kind: 'multi_session',
          sourced_facts: [{ fact: 'Three separate actions are pending.', source_memory_id: 'zara-memory', source_ref: 'zara-session', evidence_quote: 'return boots, pickup replacement, pickup blazer', confidence: 1 }],
          entity_ledger: [
            { id: 'boots', label: 'boots', type: 'item', aliases: ['replacement boots'], source_memory_ids: ['zara-memory'] },
            { id: 'blazer', label: 'blazer', type: 'item', aliases: [], source_memory_ids: ['zara-memory'] },
          ],
          event_ledger: [],
          pending_action_ledger: [
            routedEvent('return-boots', 'return', 'boots'),
            routedEvent('pickup-boots', 'pickup', 'boots'),
            routedEvent('pickup-blazer', 'pickup', 'blazer'),
          ],
          timeline: [],
          conflicts: [],
          exclusions: [],
          missing_information: [],
        }) }
      }
      parentCalls++
      const resultMessage = messages.find(message => message.role === 'tool' && message.tool_name === 'ForkEvidenceReader')
      parentSawForkResult = Boolean(resultMessage?.content.includes('"count": 3'))
      return { role: 'assistant' as const, content: 'You have 2 physical items.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('How many items did I need to pick up or return?')],
    3,
    undefined,
    { forceEvidenceReader: true, questionType: 'multi-session' },
  )

  assert.equal(parentCalls, 1)
  assert.equal(parentSawForkResult, true)
  assert.equal(result.events.some(event => event.type === 'subagent_start' && event.turn === 0), true)
  assert.equal(result.messages.some(message => message.role === 'tool' && message.tool_name === 'ForkEvidenceReader'), true)
  assert.equal(result.events.some(event => event.type === 'answer_guard_applied'), true)
  assert.equal(result.output, 'There are 3 distinct pending actions: return boots; pickup boots; pickup blazer.')
})

test('memory agent enforces a sourced no-answer decision over a parent inference', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-no-answer-guard-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('Evidence Reader Subagent'))
      if (isChild) {
        return { role: 'assistant' as const, content: JSON.stringify({
          schema_version: '1.0',
          answerability: 'no_answer',
          query_kind: 'general',
          sourced_facts: [],
          entity_ledger: [],
          event_ledger: [],
          pending_action_ledger: [],
          timeline: [],
          conflicts: [],
          exclusions: ['The stored vehicle is a red car, not a bicycle.'],
          missing_information: ['No memory states the color of the user\'s bicycle.'],
        }) }
      }
      return { role: 'assistant' as const, content: 'The bicycle was probably blue.' }
    },
  }

  const unguarded = await agent.run(
    model,
    [createUserMessage('What color is my bicycle?')],
    3,
    undefined,
    { forceEvidenceReader: true, questionType: 'single-session-user' },
  )
  assert.equal(unguarded.output, 'The bicycle was probably blue.')
  assert.equal(unguarded.events.some(event =>
    event.type === 'answer_guard_applied' && event.decisionKind === 'no_answer'), false)

  const result = await agent.run(
    model,
    [createUserMessage('What color is my bicycle?')],
    3,
    undefined,
    {
      forceEvidenceReader: true,
      questionType: 'single-session-user',
      enforceNoAnswerGuard: true,
    },
  )

  assert.match(result.output ?? '', /does not provide enough information/i)
  assert.match(result.output ?? '', /No memory states the color/i)
  assert.equal(result.output?.includes('probably blue'), false)
  assert.equal(result.events.some(event =>
    event.type === 'answer_guard_applied' && event.decisionKind === 'no_answer'), true)
})

test('orchestrator parent sees only TodoWrite and ForkSubagent while child reads memory', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'memory-orchestrator-'))
  const configPath = path.join(root, 'memory-agent.config.json')
  await writeFile(configPath, JSON.stringify({
    memoryRoot: './data',
    context: { maxItems: 4, maxChars: 4_000, minScore: 0.01 },
    compression: { maxChars: 8_000, preserveRecentChars: 2_000, summaryMaxChars: 1_000 },
  }), 'utf8')
  const agent = await createMemoryAgent(configPath)
  await agent.store.create({
    kind: 'episodic',
    title: 'Tea preference',
    summary: 'The user prefers jasmine tea.',
    content: 'user: I prefer jasmine tea in the afternoon.',
    source: source('tea-session'),
  })

  let parentTurn = 0
  let parentToolNames: string[] = []
  let parentSawInjectedMemory = false
  let childToolNames: string[] = []
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated subagent'))
      if (isChild) {
        childToolNames = context.tools.map(tool => tool.name)
        const search = messages.find(message => message.role === 'tool' && message.tool_name === 'MemorySearch')
        if (!search) {
          return assistantWithToolCalls('', [
            createToolCall('search-tea', 'MemorySearch', { query: 'afternoon tea preference' }),
          ])
        }
        return { role: 'assistant' as const, content: `Evidence: ${search.content}` }
      }

      parentTurn++
      parentToolNames = context.tools.map(tool => tool.name)
      parentSawInjectedMemory ||= messages.some(message => message.content.includes('<memory_context>'))
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [
          createToolCall('todo-open', 'TodoWrite', {
            todos: [{ content: 'Find preference evidence', activeForm: 'Finding preference evidence', status: 'in_progress' }],
          }),
          createToolCall('fork-tea', 'ForkSubagent', {
            description: 'Find tea preference',
            prompt: 'Find the user-authored afternoon tea preference and preserve its source.',
            allowed_tools: ['MemorySearch', 'MemoryRead'],
          }),
        ])
      }
      if (parentTurn === 2) {
        return assistantWithToolCalls('', [
          createToolCall('todo-done', 'TodoWrite', {
            todos: [{ content: 'Find preference evidence', activeForm: 'Finding preference evidence', status: 'completed' }],
          }),
        ])
      }
      return { role: 'assistant' as const, content: 'The user prefers jasmine tea in the afternoon.' }
    },
  }

  const result = await agent.run(
    model,
    [createUserMessage('What tea do I prefer in the afternoon?')],
    5,
    undefined,
    { parentMode: 'orchestrator', maxToolCallsPerTurn: 2 },
  )

  assert.deepEqual(parentToolNames, ['TodoWrite', 'ForkSubagent'])
  assert.deepEqual(childToolNames, ['MemorySearch', 'MemoryRead'])
  assert.equal(parentSawInjectedMemory, false)
  assert.equal(result.output, 'The user prefers jasmine tea in the afternoon.')
  assert.deepEqual(await agent.todos.get('main'), [])
  assert.equal((await agent.sidechains.list()).length, 1)
})

function routedEvent(id: string, action: string, entityId: string) {
  return {
    id,
    action,
    entity_id: entityId,
    object: entityId,
    status: 'pending',
    source_event_id: id,
  }
}
