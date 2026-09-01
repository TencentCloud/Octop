import assert from 'node:assert/strict'
import { mkdtemp } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { runAgentLoop } from '../src/core/agent-loop.js'
import { InMemoryChildSidechainStore } from '../src/core/child-sidechain.js'
import {
  createForkSubagentTool,
  extractPreservedToolEvidence,
  observeEvidenceCoverage,
} from '../src/core/fork-subagent.js'
import { createUserMessage } from '../src/core/messages.js'
import { assistantWithToolCalls, createToolCall } from '../src/core/mock-model.js'
import { createPermissionContext } from '../src/core/permissions.js'
import { InMemoryResultLedgerStore } from '../src/core/result-ledger.js'
import { createTodoWriteTool, InMemoryTodoStore } from '../src/core/todo.js'
import { buildTool } from '../src/core/tool.js'
import {
  createCompileEvidenceTool,
  normalizeCompilerCount,
  reconcileDiscourseAnswer,
  reconcileDiscoveredCoverage,
  reconcileExplicitLeadership,
  reconcileExplicitObligations,
  reconcileTruncatedCompilerConsensus,
  reconcileLatestStateAnswer,
  reconcileExplicitLatestState,
  validateCompilerAnswerContract,
  boundCompileEvidenceEnvelope,
  buildCrossSourceCoverage,
} from '../src/memory/compile-evidence-tool.js'

test('ForkSubagent isolates parent history, scopes tools, and records a child sidechain', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'fork-subagent-'))
  const permissionContext = createPermissionContext({ cwd: root, readableRoots: [root] })
  const sidechains = new InMemoryChildSidechainStore()
  const Echo = buildTool<{ value: string }, string>({
    name: 'Echo',
    inputSchema: { value: { type: 'string', required: true } },
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    call: async input => input.value,
  })
  const Hidden = buildTool({
    name: 'Hidden',
    isReadOnly: () => true,
    call: async () => 'must not be visible',
  })

  let parentTurns = 0
  let childSawParentSecret = false
  let childToolNames: string[] = []
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated subagent'),
      )
      if (isChild) {
        childSawParentSecret = messages.some(message => message.content.includes('PARENT_SECRET'))
        childToolNames = context.tools.map(tool => tool.name)
        const echoResult = messages.find(message => message.role === 'tool' && message.tool_name === 'Echo')
        if (!echoResult) {
          return assistantWithToolCalls('', [createToolCall('echo-child', 'Echo', { value: 'child evidence' })])
        }
        return { role: 'assistant' as const, content: `organized: ${echoResult.content}` }
      }

      parentTurns++
      if (parentTurns === 1) {
        return assistantWithToolCalls('', [createToolCall('fork-1', 'ForkSubagent', {
          description: 'Organize one fact',
          prompt: 'Use Echo and return its result.',
          allowed_tools: ['Echo'],
        })])
      }
      const childResult = messages.find(message => message.role === 'tool' && message.tool_name === 'ForkSubagent')
      return { role: 'assistant' as const, content: `parent received: ${childResult?.content}` }
    },
  }
  const ForkSubagent = createForkSubagentTool({
    model,
    availableTools: [Echo, Hidden],
    sidechainStore: sidechains,
  })

  const result = await runAgentLoop({
    model,
    tools: [ForkSubagent],
    permissionContext,
    messages: [createUserMessage('PARENT_SECRET: answer a broader question')],
  })

  assert.deepEqual(childToolNames, ['Echo'])
  assert.equal(childSawParentSecret, false)
  assert.match(result.output ?? '', /organized: child evidence/)
  assert.equal(result.messages.some(message => message.content.includes('Use Echo and return its result.')), false)
  assert.equal(result.events.some(event => event.type === 'subagent_start'), true)
  assert.equal(result.events.some(event => event.type === 'subagent_end'), true)

  const records = await sidechains.list()
  assert.equal(records.length, 1)
  assert.equal(records[0]?.status, 'completed')
  assert.deepEqual(records[0]?.allowedTools, ['Echo'])
  assert.equal(records[0]?.messages.some(message => message.role === 'tool' && message.tool_name === 'Echo'), true)
})

test('ForkSubagent injects resolved navigation context only into the child sidechain', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'fork-context-prelude-'))
  const Noop = buildTool({
    name: 'Noop',
    isReadOnly: () => true,
    call: async () => 'unused',
  })
  let parentTurn = 0
  let childSawPrelude = false
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated subagent'))
      if (isChild) {
        childSawPrelude = messages.some(message =>
          message.role === 'user' && message.content.includes('speaker:user exact event preview'))
        return { role: 'assistant' as const, content: 'child report' }
      }
      parentTurn++
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('fork-context', 'ForkSubagent', {
          description: 'Read one event',
          prompt: 'Audit the referenced source.',
          allowed_tools: ['Noop'],
          context_refs: ['frontmatter-1'],
        })])
      }
      return { role: 'assistant' as const, content: 'parent done' }
    },
  }
  const ForkSubagent = createForkSubagentTool({
    model,
    availableTools: [Noop],
    resolveContextPrelude: async refs => `refs:${refs.join(',')} speaker:user exact event preview`,
  })

  const result = await runAgentLoop({
    model,
    tools: [ForkSubagent],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('PARENT_SECRET')],
  })

  assert.equal(childSawPrelude, true)
  assert.equal(result.messages.some(message => message.content.includes('exact event preview')), false)
})

test('TodoWrite replaces scoped parent state and clears storage when all work is complete', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'todo-write-'))
  const store = new InMemoryTodoStore()
  const TodoWrite = createTodoWriteTool({ store, scopeId: 'parent' })
  let turn = 0
  const model = {
    async next() {
      turn++
      if (turn === 1) {
        return assistantWithToolCalls('', [createToolCall('todo-1', 'TodoWrite', {
          todos: [
            { content: 'Collect evidence', activeForm: 'Collecting evidence', status: 'in_progress' },
            { content: 'Answer user', activeForm: 'Answering user', status: 'pending' },
          ],
        })])
      }
      if (turn === 2) {
        return assistantWithToolCalls('', [createToolCall('todo-2', 'TodoWrite', {
          todos: [
            { content: 'Collect evidence', activeForm: 'Collecting evidence', status: 'completed' },
            { content: 'Answer user', activeForm: 'Answering user', status: 'completed' },
          ],
        })])
      }
      return { role: 'assistant' as const, content: 'done' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [TodoWrite],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('do the work')],
  })

  assert.equal(result.output, 'done')
  assert.deepEqual(await store.get('parent'), [])
  const writes = result.messages.filter(message => message.role === 'tool' && message.tool_name === 'TodoWrite')
  assert.equal(writes.length, 2)
  assert.match(writes[1]?.content ?? '', /Collect evidence/)
})

test('TodoWrite normalizes an omitted display form from the semantic task text', async () => {
  const store = new InMemoryTodoStore()
  const TodoWrite = createTodoWriteTool({ store, scopeId: 'normalized' })
  const input = {
    todos: [{ content: 'Compile sourced evidence', activeForm: '', status: 'in_progress' as const }],
  }

  assert.deepEqual(await TodoWrite.validateInput(input, {} as never), { result: true })
  await TodoWrite.call(input, {} as never)
  assert.deepEqual(await store.get('normalized'), [{
    content: 'Compile sourced evidence',
    activeForm: 'Compile sourced evidence',
    status: 'in_progress',
  }])
})

test('ForkSubagent reserves its final turn to return evidence after tool budget exhaustion', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'fork-final-turn-'))
  const sidechains = new InMemoryChildSidechainStore()
  const Search = buildTool({
    name: 'Search',
    isReadOnly: () => true,
    call: async () => 'sourced evidence',
  })
  let parentTurn = 0
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[], context: import('../src/core/agent-loop.js').ModelContext) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated subagent'))
      if (isChild) {
        if (context.tools.length > 0) {
          return assistantWithToolCalls('', [createToolCall(`search-${context.turn}`, 'Search', {})])
        }
        return { role: 'assistant' as const, content: 'final child report from sourced evidence' }
      }
      parentTurn++
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('fork-budget', 'ForkSubagent', {
          description: 'Collect bounded evidence',
          prompt: 'Search until the tool budget ends, then report.',
          allowed_tools: ['Search'],
          max_turns: 2,
        })])
      }
      const toolResult = messages.find(message =>
        message.role === 'tool' && message.tool_name === 'ForkSubagent')
      return { role: 'assistant' as const, content: toolResult?.content ?? '' }
    },
  }
  const ForkSubagent = createForkSubagentTool({
    model,
    availableTools: [Search],
    sidechainStore: sidechains,
  })

  const result = await runAgentLoop({
    model,
    tools: [ForkSubagent],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('delegate')],
  })

  assert.match(result.output ?? '', /final child report from sourced evidence/)
  assert.equal((await sidechains.list())[0]?.status, 'completed')
})

test('ForkSubagent ledger mode keeps the complete result out of parent context', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'fork-result-ledger-'))
  const resultLedger = new InMemoryResultLedgerStore()
  const sidechains = new InMemoryChildSidechainStore()
  const Noop = buildTool({
    name: 'Noop',
    isReadOnly: () => true,
    call: async () => 'unused',
  })
  const completeOutput = `${'bounded evidence '.repeat(20)}FULL_RESULT_TAIL`
  let parentTurn = 0
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isChild = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated subagent'))
      if (isChild) return { role: 'assistant' as const, content: completeOutput }
      parentTurn++
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('fork-ledger', 'ForkSubagent', {
          description: 'Collect evidence',
          prompt: 'Return the bounded report.',
          allowed_tools: ['Noop'],
        })])
      }
      const toolResult = messages.find(message =>
        message.role === 'tool' && message.tool_name === 'ForkSubagent')
      return { role: 'assistant' as const, content: toolResult?.content ?? '' }
    },
  }
  const ForkSubagent = createForkSubagentTool({
    model,
    availableTools: [Noop],
    sidechainStore: sidechains,
    resultLedger,
    resultMode: 'ledger',
  })

  const result = await runAgentLoop({
    model,
    tools: [ForkSubagent],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('delegate without copying the full result')],
  })

  assert.doesNotMatch(result.output ?? '', /FULL_RESULT_TAIL/)
  assert.match(result.output ?? '', /result_id/)
  const records = await resultLedger.list()
  assert.equal(records.length, 1)
  assert.match(records[0]?.output ?? '', /FULL_RESULT_TAIL/)
  assert.ok((records[0]?.summary.length ?? 0) <= 200)
})

test('CompileEvidence resolves full ledger results inside an isolated compiler sidechain', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'compile-evidence-'))
  const resultLedger = new InMemoryResultLedgerStore()
  const sidechains = new InMemoryChildSidechainStore()
  await resultLedger.put({
    id: 'result-a',
    subagentId: 'child-a',
    kind: 'general',
    description: 'First source',
    objective: 'Find first candidate',
    status: 'completed',
    summary: 'first summary',
    output: 'FULL_SOURCE_A happened on 2025-01-03',
  })
  await resultLedger.put({
    id: 'result-b',
    subagentId: 'child-b',
    kind: 'general',
    description: 'Second source',
    objective: 'Find second candidate',
    status: 'completed',
    summary: 'second summary',
    output: 'FULL_SOURCE_B was explicitly excluded',
  })

  let parentTurn = 0
  let compilerSawCompleteResults = false
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isCompiler = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated evidence compiler'))
      if (isCompiler) {
        compilerSawCompleteResults = messages.some(message =>
          message.content.includes('FULL_SOURCE_A') && message.content.includes('FULL_SOURCE_B'))
        return { role: 'assistant' as const, content: 'compiled packet with result-a and result-b' }
      }
      const isRepair = messages.some(message =>
        message.role === 'system' && message.content.includes('repair one truncated evidence compiler response'))
      if (isRepair) return { role: 'assistant' as const, content: 'repair remained unparseable' }
      parentTurn++
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('compile-1', 'CompileEvidence', {
          objective: 'Resolve the cross-source answer',
          result_ids: ['result-a'],
        })])
      }
      const toolResult = messages.find(message =>
        message.role === 'tool' && message.tool_name === 'CompileEvidence')
      return { role: 'assistant' as const, content: toolResult?.content ?? '' }
    },
  }
  const CompileEvidence = createCompileEvidenceTool({ model, resultLedger, sidechainStore: sidechains })

  const result = await runAgentLoop({
    model,
    tools: [CompileEvidence],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [
      createUserMessage('compile the delegated evidence'),
      {
        role: 'tool',
        tool_call_id: 'prior-fork',
        tool_name: 'ForkSubagent',
        is_error: false,
        content: JSON.stringify({ result_id: 'result-b' }),
      },
    ],
  })

  assert.equal(compilerSawCompleteResults, true)
  assert.match(result.output ?? '', /result-a/)
  assert.match(result.output ?? '', /compiler subagent returned no parseable packet/i)
  const compilerSidechains = await sidechains.list()
  assert.equal(compilerSidechains.length, 2)
  assert.equal(compilerSidechains[0]?.kind, 'evidence_compiler')
  assert.equal(compilerSidechains[1]?.description, 'Repair truncated evidence packet')
})

test('CompileEvidence restores explicit user actions merged by the compiler', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'compile-obligations-'))
  const resultLedger = new InMemoryResultLedgerStore()
  const sidechains = new InMemoryChildSidechainStore()
  await resultLedger.put({
    id: 'result-actions',
    subagentId: 'child-actions',
    kind: 'general',
    description: 'Audit clothing obligations',
    objective: 'Find clothing pickup and return tasks',
    status: 'completed',
    summary: 'Two physical items were discussed.',
    output: '{}',
    contextPrelude: `Bounded Event Ledger excerpts\n${JSON.stringify([
      { memory_id: 'm1', source_ref: 's1', turn_ref: 's1#turn-0', speaker: 'user', source_date: '2025-01-01', excerpt: 'user: I need to return some boots to Zara, actually.' },
      { memory_id: 'm2', source_ref: 's2', turn_ref: 's2#turn-0', speaker: 'user', source_date: '2025-01-01', excerpt: 'user: I still need to pick up the new pair of boots.' },
      { memory_id: 'm3', source_ref: 's3', turn_ref: 's3#turn-0', speaker: 'user', source_date: '2025-01-01', excerpt: 'user: I still need to pick up my navy blazer.' },
      { memory_id: 'm4', source_ref: 's4', turn_ref: 's4#turn-0', speaker: 'user', source_date: '2025-01-01', excerpt: 'user: Do you have tips for tracking items I need to pick up or return?' },
    ])}`,
  })

  let parentTurn = 0
  const model = {
    async next(messages: readonly import('../src/core/messages.js').Message[]) {
      const isCompiler = messages.some(message =>
        message.role === 'system' && message.content.includes('isolated evidence compiler'))
      if (isCompiler) {
        return { role: 'assistant' as const, content: '' }
      }
      parentTurn++
      if (parentTurn === 1) {
        return assistantWithToolCalls('', [createToolCall('compile-actions', 'CompileEvidence', {
          objective: 'Compile clothing pickup and return evidence.',
          result_ids: ['result-actions'],
        })])
      }
      const toolResult = messages.find(message => message.role === 'tool' && message.tool_name === 'CompileEvidence')
      return { role: 'assistant' as const, content: toolResult?.content ?? '' }
    },
  }
  const CompileEvidence = createCompileEvidenceTool({
    model,
    resultLedger,
    sidechainStore: sidechains,
    taskContext: 'How many clothing items do I need to pick up or return?',
  })
  const result = await runAgentLoop({
    model,
    tools: [CompileEvidence],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('compile explicit obligations')],
  })

  const toolEnvelope = JSON.parse(result.output ?? '{}') as { evidence_packet?: Record<string, unknown> }
  const packet = toolEnvelope.evidence_packet as { derived_count?: number; included?: unknown[]; excluded?: unknown[] }
  assert.equal(packet.derived_count, 3)
  assert.equal(packet.included?.length, 3)
  assert.equal(packet.excluded?.length, 0)
})

test('explicit obligation reconciliation corrects a weakened included action and mismatched count', () => {
  const raw = JSON.stringify({
    answerability: 'partial',
    count_contract: 'deterministic',
    derived_count: 2,
    derived_answer: 'Two pickups and one uncertain return.',
    included: [
      { id: 'pickup-boots', claim: 'Boot pickup is pending.', result_ids: ['r1'], source_refs: ['s1'] },
      { id: 'pickup-blazer', claim: 'Blazer pickup is pending.', result_ids: ['r1'], source_refs: ['s2'] },
      { id: 'return-boots', claim: 'Boot return is unclear.', result_ids: ['r1'], source_refs: ['s3'] },
    ],
    excluded: [],
  })
  const reconciled = JSON.parse(reconcileExplicitObligations(
    'How many items do I need to pick up or return? Give the total count.',
    raw,
    [{ action: 'return', object: 'some boots', quote: 'I need to return some boots.', result_ids: ['r1'], source_refs: ['s3'] }],
  )) as { derived_count?: number; included?: Array<{ claim?: string; status?: string }> }

  assert.equal(reconciled.derived_count, 3)
  assert.equal(reconciled.included?.[2]?.status, 'pending')
  assert.match(reconciled.included?.[2]?.claim ?? '', /Explicit user obligation/)
})

test('explicit obligation reconciliation does not rewrite non-action count questions', () => {
  const raw = JSON.stringify({
    derived_count: 4,
    included: Array.from({ length: 6 }, (_, index) => ({ id: `e${index}`, claim: `Evidence ${index}` })),
  })
  assert.equal(reconcileExplicitObligations('How many Korean restaurants have I tried?', raw, []), raw)
  assert.equal(reconcileExplicitObligations('How many Korean restaurants have I tried? Collect all evidence.', raw, []), raw)
})

test('result evidence preservation keeps exact user windows from MemoryRead', () => {
  const preserved = extractPreservedToolEvidence([{
    role: 'tool',
    tool_call_id: 'read-1',
    tool_name: 'MemoryRead',
    is_error: false,
    content: JSON.stringify({
      id: 'raw-1',
      source: { ref: 'session-1' },
      source_refs: ['session-1#turn-0'],
      temporal: { event_time: '2023/02/05' },
      content: 'user: I helped my friend prepare a nursery today.\nassistant: That was thoughtful.',
      read_window: { offset: 0 },
    }),
  }])

  assert.match(preserved, /helped my friend prepare a nursery today/)
  assert.doesNotMatch(preserved, /That was thoughtful/)
})

test('coverage observation detects search saturation and unread source windows', () => {
  const searchMessage = (id: string): import('../src/core/messages.js').Message => ({
    role: 'tool',
    tool_call_id: id,
    tool_name: 'MemorySearch',
    is_error: false,
    content: JSON.stringify([{
      id: 'event-a',
      kind: 'event',
      source_ref: 'session-a',
      summary_complete: true,
      summary: 'One complete event.',
    }]),
  })
  const saturated = observeEvidenceCoverage([
    searchMessage('search-1'),
    searchMessage('search-2'),
    searchMessage('search-3'),
  ])
  assert.equal(saturated.search_calls, 3)
  assert.equal(saturated.trailing_searches_without_new_sources, 2)
  assert.deepEqual(saturated.inspected_source_refs, ['session-a'])

  const unread = observeEvidenceCoverage([{
    role: 'tool',
    tool_call_id: 'read-1',
    tool_name: 'MemoryRead',
    is_error: false,
    content: JSON.stringify({
      id: 'raw-a',
      source: { ref: 'session-a' },
      content: 'user: relevant evidence',
      read_window: { offset: 0, has_more: true, next_offset: 1000 },
    }),
  }], 'Prelude [{"source_ref":"session-a"}]')
  assert.deepEqual(unread.assigned_source_refs, ['session-a'])
  assert.deepEqual(unread.unread_source_refs, ['session-a'])
})

test('compiler answer contract commits only sourced question-conditioned projections', () => {
  const committed = validateCompilerAnswerContract({
    answerability: 'answerable',
    coverage_status: 'complete',
    included: [{ id: 'state-a', claim: 'Latest state is active.' }],
    excluded: [{ id: 'old-state', claim: 'Older state.' }],
    conflicts: [],
    unexplored_sources: [],
    answer_contract: {
      operation: 'latest_state',
      final_answer: 'The latest state is active.',
      included_ids: ['state-a'],
      excluded_ids: ['old-state'],
    },
  })
  assert.equal(committed?.projection_status, 'committed')

  const review = validateCompilerAnswerContract({
    answerability: 'answerable',
    coverage_status: 'complete',
    included: [{ id: 'state-a', claim: 'Latest state is active.' }],
    conflicts: [],
    answer_contract: {
      operation: 'latest_state',
      final_answer: 'An unsupported state.',
      included_ids: ['unknown-id'],
      excluded_ids: [],
    },
  })
  assert.equal(review?.projection_status, 'review')

  const duration = validateCompilerAnswerContract({
    answerability: 'answerable',
    coverage_status: 'incomplete',
    included: [{ id: 'start' }, { id: 'end' }],
    conflicts: [],
    answer_contract: {
      operation: 'duration',
      final_answer: '5 days',
      included_ids: ['start', 'end'],
      excluded_ids: [],
    },
  })
  assert.equal(duration?.projection_status, 'committed')

  const contradictoryCount = validateCompilerAnswerContract({
    answerability: 'answerable',
    coverage_status: 'complete',
    included: [{ id: 'evidence-a' }, { id: 'evidence-b' }],
    conflicts: [],
    answer_contract: {
      operation: 'count',
      final_answer: '25 postcards',
      included_ids: ['evidence-a', 'evidence-b'],
      excluded_ids: [],
    },
    derived_count: 2,
  })
  assert.equal(contradictoryCount?.projection_status, 'review')

  const preference = validateCompilerAnswerContract({
    answerability: 'answerable',
    coverage_status: 'complete',
    included: [{ id: 'preference-a' }],
    conflicts: [],
    answer_contract: {
      operation: 'preference',
      final_answer: 'Use the existing Suica card and TripIt itinerary as personalization anchors.',
      included_ids: ['preference-a'],
      excluded_ids: [],
    },
  })
  assert.equal(preference?.projection_status, 'constraints_only')
})

test('cross-source coverage allows one complete child to close an older scoped gap', () => {
  const incomplete = {
    id: 'result-incomplete',
    subagentId: 'child-incomplete',
    kind: 'general',
    description: 'Initial audit',
    objective: 'Find all facts',
    status: 'completed' as const,
    summary: 'Found one fact but left source-b unread.',
    output: '{}',
    evidenceFactValid: true,
    evidenceCoverageComplete: false,
    evidenceResult: {
      schema_version: '1.1' as const,
      task: 'Find all facts',
      candidates: [],
      covered_memory_ids: [],
      covered_source_refs: ['source-a'],
      unexplored_source_refs: ['source-b'],
      conflicts: [],
      missing_information: [],
      coverage_status: 'incomplete' as const,
      coverage: {
        inspected_source_refs: ['source-a'],
        unresolved_source_refs: ['source-b'],
        stop_reason: 'unresolved_sources' as const,
      },
    },
  }
  const repair = {
    ...incomplete,
    id: 'result-repair',
    subagentId: 'child-repair',
    description: 'Repair source-b',
    summary: 'Inspected source-b.',
    evidenceCoverageComplete: true,
    evidenceResult: {
      ...incomplete.evidenceResult,
      covered_source_refs: ['source-b'],
      unexplored_source_refs: [],
      coverage_status: 'complete' as const,
      coverage: {
        inspected_source_refs: ['source-b'],
        unresolved_source_refs: [],
        stop_reason: 'assigned_scope_exhausted' as const,
      },
    },
  }

  const before = buildCrossSourceCoverage([incomplete])
  assert.equal(before.status, 'incomplete')
  assert.deepEqual(before.unresolved_source_refs, ['source-b'])

  const after = buildCrossSourceCoverage([incomplete, repair])
  assert.equal(after.status, 'complete')
  assert.deepEqual(after.unresolved_source_refs, [])
  assert.deepEqual(after.incomplete_result_ids, [])
})

test('compiler envelope stays below the tool batch boundary without losing its projection', () => {
  const bounded = boundCompileEvidenceEnvelope({
    status: 'completed',
    result_ids: ['result-a', 'result-b'],
    compiler_repair_attempted: false,
    cross_source_coverage: {
      status: 'incomplete',
      unresolved_source_refs: Array.from({ length: 40 }, (_, index) => `source-${index}`),
    },
    evidence_packet: {
      answerability: 'answerable',
      derived_answer: 'A'.repeat(2_000),
      answer_contract: {
        operation: 'temporal_order',
        final_answer: 'First A, then B.',
        included_ids: ['a', 'b'],
        excluded_ids: [],
        projection_status: 'committed',
      },
      included_count: 20,
      included: Array.from({ length: 20 }, (_, index) => ({
        id: `item-${index}`,
        claim: 'C'.repeat(300),
        source_refs: Array.from({ length: 10 }, (_, source) => `source-${source}`),
      })),
      conflicts: Array.from({ length: 20 }, () => 'conflict'.repeat(30)),
      missing_information: Array.from({ length: 20 }, () => 'missing'.repeat(30)),
      coverage_status: 'incomplete',
    },
  })

  assert.ok(JSON.stringify(bounded).length <= 1_800)
  const packet = bounded.evidence_packet as Record<string, unknown>
  assert.equal((packet.answer_contract as Record<string, unknown>).projection_status, 'committed')
})

test('compiler count normalization uses included task units instead of a contradictory model count', () => {
  const raw = JSON.stringify({
    answerability: 'partial',
    count_contract: 'deterministic',
    derived_count: 0,
    included: [
      { id: 'class-project', claim: 'User led the analysis team in a class project.', source_refs: ['s1#turn-0'] },
      { id: 'engineering-team', claim: 'User is leading an engineering team.', source_refs: ['s2#turn-0'] },
    ],
    excluded: [
      { id: 'completed-project', claim: 'User completed a project but did not say they led it.', source_refs: ['s2#turn-2'] },
    ],
  })
  const packet = JSON.parse(normalizeCompilerCount(
    'How many projects have I led or am currently leading?',
    raw,
  )) as { derived_count?: number; included?: unknown[] }

  assert.equal(packet.derived_count, 2)
  assert.equal(packet.included?.length, 2)
})

test('leadership reconciliation counts explicit lead predicates and discards completion-only candidates', () => {
  const raw = JSON.stringify({
    answerability: 'partial',
    derived_count: 3,
    included: [
      { id: 'class-project', claim: 'User led a team.', source_refs: ['s1#turn-0'] },
      { id: 'completed-project', claim: 'User completed a project.', source_refs: ['s2#turn-2'] },
      { id: 'current-team', claim: 'User is leading a team.', source_refs: ['s2#turn-0'] },
    ],
  })
  const packet = JSON.parse(reconcileExplicitLeadership(
    'How many projects have I led or am currently leading?',
    raw,
    [
      { object: 'data analysis team', quote: 'I led the data analysis team', result_ids: ['r1'], source_refs: ['s1#turn-0'] },
      { object: 'team of five engineers', quote: 'I have been leading a team of five engineers', result_ids: ['r2'], source_refs: ['s2#turn-0'] },
    ],
  )) as { count_contract?: string; derived_count?: number; included?: Array<{ claim?: string }> }

  assert.equal(packet.count_contract, 'deterministic')
  assert.equal(packet.derived_count, 2)
  assert.equal(packet.included?.length, 2)
  assert.doesNotMatch(packet.included?.map(item => item.claim).join(' ') ?? '', /completed/i)
})

test('discovered coverage reconciliation cleans a census without creating units from raw hits', () => {
  const raw = JSON.stringify({
    answerability: 'partial',
    derived_count: 1,
    included: [
      { id: 'existing-kit', claim: 'User worked on a Spitfire.', source_refs: ['kits-a#turn-0'] },
      { id: 'duplicate-kit', claim: 'User worked on the Spitfire and adjusted its finish.', source_refs: ['kits-a#turn-2'] },
      { id: 'generic-kits', claim: 'Unspecified model tanks (plural), not named as distinct kits.', source_refs: ['kits-b#turn-0'] },
    ],
    excluded: [],
  })
  const packet = JSON.parse(reconcileDiscoveredCoverage(
    'How many model kits have I worked on or bought?',
    raw,
    [{
      quote: 'I started working on a diorama featuring a 1/16 scale tank.',
      result_ids: ['result-1'],
      source_refs: ['kits-b#turn-0'],
      source_date: '2023/05/29',
    }],
  )) as { included?: Array<{ source_refs?: string[] }>; reconciliation?: string }

  assert.equal(packet.included?.length, 1)
  assert.deepEqual(packet.included?.[0]?.source_refs, ['kits-a#turn-0'])
  assert.doesNotMatch(JSON.stringify(packet), /diorama featuring/)
  assert.match(packet.reconciliation ?? '', /removed 2 duplicate or unidentifiable/i)
})

test('discourse reconciliation promotes one uniquely implied location without naming an entity in code', () => {
  const raw = JSON.stringify({
    answerability: 'partial',
    derived_answer: 'Northwind is contextually implied by the surrounding same-session context but not repeated in the event sentence.',
    included: [{ id: 'context', claim: 'The user regularly shops at Northwind.' }],
  })
  const packet = JSON.parse(reconcileDiscourseAnswer('Where did I redeem the coupon?', raw)) as {
    answerability?: string
    discourse_answer?: string
  }

  assert.equal(packet.answerability, 'answerable')
  assert.equal(packet.discourse_answer, 'Northwind')
})

test('discourse reconciliation recovers one repeated same-source proper location entity', () => {
  const packet = JSON.parse(reconcileDiscourseAnswer(
    'Where did I use the coupon?',
    JSON.stringify({
      derived_answer: 'The store is not explicit. Northwind is discussed in the same conversation.',
      included: [
        { claim: 'User uses the Northwind Rewards app.', source_refs: ['session-a#turn-2'] },
        { claim: 'Assistant discussed Northwind coupons.', source_refs: ['session-a#turn-5'] },
      ],
    }),
  )) as { discourse_answer?: string }

  assert.equal(packet.discourse_answer, 'Northwind')
})

test('discourse reconciliation may use excluded context from the same source', () => {
  const packet = JSON.parse(reconcileDiscourseAnswer(
    'Where did I redeem it?',
    JSON.stringify({
      included: [{ claim: 'Coupon redemption sentence omitted the location.', source_refs: ['session-b#turn-4'] }],
      excluded: [
        { claim: 'User regularly shops at Northwind.', source_refs: ['session-b#turn-6'] },
        { claim: 'Assistant discussed Northwind email coupons.', source_refs: ['session-b#turn-5'] },
      ],
    }),
  )) as { discourse_answer?: string }

  assert.equal(packet.discourse_answer, 'Northwind')
})

test('discourse reconciliation ignores instructional where clauses', () => {
  const raw = JSON.stringify({
    included: [{ claim: 'User prefers Premiere resources.', source_refs: ['session-c#turn-0'] }],
  })
  assert.equal(reconcileDiscourseAnswer(
    'Can you recommend resources where I can learn video editing?',
    raw,
  ), raw)
})

test('discovered sources do not create an entity count from an empty compiler census', () => {
  const raw = JSON.stringify({ answerability: 'partial', derived_count: null, included: [] })
  assert.equal(reconcileDiscoveredCoverage(
    'How many model kits have I worked on?',
    raw,
    [{
      quote: 'I started working on a 1/16 scale named model.',
      result_ids: ['r1'],
      source_refs: ['s1#turn-0'],
    }],
  ), raw)
})

test('truncated compiler count becomes a contract only when fallback units independently agree', () => {
  const fallback = JSON.stringify({
    answerability: 'partial',
    derived_count: null,
    included: [
      { id: 'a', claim: 'First named item.' },
      { id: 'b', claim: 'Second named item.' },
    ],
  })
  const truncated = '{"answerability":"partial","derived_count":2,"derived_answer":"Two named items","included":[{"id":"a"}'
  const packet = JSON.parse(reconcileTruncatedCompilerConsensus(
    'How many named items are there?',
    truncated,
    fallback,
  )) as { count_contract?: string; derived_count?: number; reconciliation?: string }

  assert.equal(packet.count_contract, 'deterministic')
  assert.equal(packet.derived_count, 2)
  assert.match(packet.reconciliation ?? '', /independently matched/)

  const disagreement = reconcileTruncatedCompilerConsensus(
    'How many named items are there?',
    truncated.replace('"derived_count":2', '"derived_count":3'),
    fallback,
  )
  assert.equal(disagreement, fallback)
})

test('truncated compiler recovers a complete sourced census when the tail is missing', () => {
  const fallback = JSON.stringify({
    answerability: 'partial',
    derived_count: null,
    included: [],
    coverage_status: 'uncertain',
  })
  const truncated = [
    '{"answerability":"answerable","derived_count":2,"derived_answer":"Two kits.","included":[',
    '{"id":"kit-a","claim":"User finished Kit A.","source_refs":["session-a#turn-0"]},',
    '{"id":"kit-b","claim":"User bought Kit B.","source_refs":["session-b#turn-2"]}',
    '],"missing_information":["provider cut the tail',
  ].join('')
  const packet = JSON.parse(reconcileTruncatedCompilerConsensus(
    'How many kits have I finished or bought?',
    truncated,
    fallback,
    ['session-a#turn-0', 'session-b#turn-2'],
  )) as { count_contract?: string; derived_count?: number; included?: unknown[]; coverage_status?: string }

  assert.equal(packet.count_contract, 'deterministic')
  assert.equal(packet.derived_count, 2)
  assert.equal(packet.included?.length, 2)
  assert.equal(packet.coverage_status, 'uncertain')

  const withExtraRef = reconcileTruncatedCompilerConsensus(
    'How many kits have I finished or bought?',
    truncated.replace('session-a#turn-0', 'session-a#turn-0","memory-uuid-a'),
    fallback,
    ['session-a#turn-0', 'session-b#turn-2'],
  )
  assert.equal((JSON.parse(withExtraRef) as { derived_count?: number }).derived_count, 2)

  const hallucinated = reconcileTruncatedCompilerConsensus(
    'How many kits have I finished or bought?',
    truncated.replace('session-b#turn-2', 'unknown-session#turn-2'),
    fallback,
    ['session-a#turn-0', 'session-b#turn-2'],
  )
  assert.equal(hallucinated, fallback)
})

test('latest state reconciliation selects the newest explicit move destination', () => {
  const packet = JSON.parse(reconcileLatestStateAnswer(
    'Where did Morgan relocate to most recently?',
    JSON.stringify({
      included: [
        { claim: 'User said Morgan moved to Harbor City.', source_date: '2023/05/24' },
        { claim: 'User said Morgan moved back to the suburbs again.', source_date: '2023/05/27' },
      ],
    }),
  )) as { state_answer?: string }

  assert.equal(packet.state_answer, 'the suburbs')
})

test('explicit state audit overrides an older compiler state with the latest sourced transition', () => {
  const packet = JSON.parse(reconcileExplicitLatestState(
    'Where did Rachel move to after her recent relocation?',
    JSON.stringify({
      answerability: 'partial',
      state_answer: 'Chicago',
      included: [{ claim: 'Rachel moved to Chicago.', source_date: '2023/05/24' }],
    }),
    [
      { destination: 'Chicago', quote: 'She moved to Chicago.', result_ids: ['r1'], source_refs: ['s1'], source_date: '2023/05/24' },
      { destination: 'the suburbs', quote: 'Rachel moved back to the suburbs again.', result_ids: ['r2'], source_refs: ['s2'], source_date: '2023/05/27' },
    ],
  )) as { state_answer?: string; derived_answer?: string }

  assert.equal(packet.state_answer, 'the suburbs')
  assert.match(packet.derived_answer ?? '', /^the suburbs\./)
})
