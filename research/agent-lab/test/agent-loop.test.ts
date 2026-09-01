import assert from 'node:assert/strict'
import { mkdtemp, readFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { setTimeout } from 'node:timers/promises'

import { createPermissionContext } from '../src/core/permissions.js'
import { createUserMessage, runAgentLoop } from '../src/core/agent-loop.js'
import { buildTool } from '../src/core/tool.js'
import {
  ScriptedModel,
  assistantWithToolCalls,
  createToolCall,
} from '../src/core/mock-model.js'
import { ReadFileTool } from '../src/tools/read-file.js'
import { WriteFileTool } from '../src/tools/write-file.js'

test('agent loop executes tools and feeds tool results back to the model', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))
  const filePath = path.join(root, 'memory', 'note.md')

  const model = new ScriptedModel([
    assistantWithToolCalls('writing memory packet', [
      createToolCall('tool_1', 'WriteFile', {
        file_path: filePath,
        content: 'fact: retrieval is not reading\n',
      }),
    ]),
    assistantWithToolCalls('reading memory packet', [
      createToolCall('tool_2', 'ReadFile', {
        file_path: filePath,
      }),
    ]),
    messages => {
      const readResult = messages.findLast(
        message => message.role === 'tool' && message.tool_name === 'ReadFile',
      )
      return {
        role: 'assistant',
        content: `final answer saw: ${readResult?.content}`,
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [ReadFileTool, WriteFileTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
      writableRoots: [path.join(root, 'memory')],
    }),
    messages: [createUserMessage('write then read')],
  })

  assert.equal(result.status, 'completed')
  assert.match(String(result.output), /retrieval is not reading/)
  assert.equal(await readFile(filePath, 'utf8'), 'fact: retrieval is not reading\n')
})

test('agent loop returns permission errors as tool results', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))
  const outsidePath = path.join(os.tmpdir(), 'outside-agent-lab.txt')

  const model = new ScriptedModel([
    assistantWithToolCalls('attempting unsafe write', [
      createToolCall('tool_1', 'WriteFile', {
        file_path: outsidePath,
        content: 'should not write\n',
      }),
    ]),
    messages => {
      const denied = messages.findLast(message => message.role === 'tool')
      return {
        role: 'assistant',
        content: `observed denial: ${denied?.content}`,
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [ReadFileTool, WriteFileTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
      writableRoots: [path.join(root, 'memory')],
    }),
    messages: [createUserMessage('try unsafe write')],
  })

  assert.equal(result.status, 'completed')
  assert.match(String(result.output), /Permission denied/)
  assert.equal(
    result.messages.some(message => message.role === 'tool' && message.is_error),
    true,
  )
})

test('agent loop validates tool input before execution', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))

  const model = new ScriptedModel([
    assistantWithToolCalls('bad write call', [
      createToolCall('tool_1', 'WriteFile', {
        file_path: path.join(root, 'memory', 'bad.md'),
      }),
    ]),
    messages => {
      const errorResult = messages.findLast(message => message.role === 'tool')
      return {
        role: 'assistant',
        content: errorResult?.content ?? '',
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [ReadFileTool, WriteFileTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
      writableRoots: [path.join(root, 'memory')],
    }),
    messages: [createUserMessage('bad input')],
  })

  assert.equal(result.status, 'completed')
  assert.match(String(result.output), /content is required/)
})

test('agent loop runs tool semantic validation before permissions and execution', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))
  let wasCalled = false

  const PositiveScoreTool = buildTool<{ score: number }, string>({
    name: 'PositiveScore',
    inputSchema: {
      score: { type: 'number', required: true },
    },
    isReadOnly: () => true,
    validateInput: async input =>
      input.score > 0
        ? { result: true }
        : { result: false, message: 'score must be greater than zero' },
    async call() {
      wasCalled = true
      return 'accepted'
    },
  })

  const model = new ScriptedModel([
    assistantWithToolCalls('bad score call', [
      createToolCall('tool_1', 'PositiveScore', { score: -1 }),
    ]),
    messages => {
      const errorResult = messages.findLast(message => message.role === 'tool')
      return {
        role: 'assistant',
        content: errorResult?.content ?? '',
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [PositiveScoreTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
    }),
    messages: [createUserMessage('validate score')],
  })

  assert.equal(result.status, 'completed')
  assert.equal(wasCalled, false)
  assert.match(String(result.output), /score must be greater than zero/)
})

test('agent loop truncates oversized tool results before feeding them back', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))

  const LongOutputTool = buildTool({
    name: 'LongOutput',
    maxResultSizeChars: 12,
    isReadOnly: () => true,
    async call() {
      return 'abcdefghijklmnopqrstuvwxyz'
    },
  })

  const model = new ScriptedModel([
    assistantWithToolCalls('long output call', [
      createToolCall('tool_1', 'LongOutput'),
    ]),
    messages => {
      const toolResult = messages.findLast(message => message.role === 'tool')
      return {
        role: 'assistant',
        content: toolResult?.content ?? '',
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [LongOutputTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
    }),
    messages: [createUserMessage('truncate output')],
  })

  assert.equal(result.status, 'completed')
  assert.match(String(result.output), /^abcdefghijkl/)
  assert.match(String(result.output), /\[truncated: 14 chars omitted\]/)
})

test('agent loop runs consecutive concurrency-safe tools in the same batch', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-lab-'))
  const order: string[] = []

  const ConcurrentReadTool = buildTool<{ label: string }, string>({
    name: 'ConcurrentRead',
    inputSchema: {
      label: { type: 'string', required: true },
    },
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    async call(input) {
      order.push(`start-${input.label}`)
      await setTimeout(20)
      order.push(`end-${input.label}`)
      return `read-${input.label}`
    },
  })

  const model = new ScriptedModel([
    assistantWithToolCalls('parallel read calls', [
      createToolCall('tool_1', 'ConcurrentRead', { label: 'a' }),
      createToolCall('tool_2', 'ConcurrentRead', { label: 'b' }),
    ]),
    messages => {
      const toolResults = messages
        .filter(message => message.role === 'tool')
        .map(message => message.content)
        .join(',')
      return {
        role: 'assistant',
        content: toolResults,
      }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [ConcurrentReadTool],
    permissionContext: createPermissionContext({
      cwd: root,
      readableRoots: [root],
    }),
    messages: [createUserMessage('read both')],
  })

  assert.equal(result.status, 'completed')
  assert.deepEqual(order.slice(0, 2), ['start-a', 'start-b'])
  assert.equal(result.output, 'read-a,read-b')
})

test('agent loop bounds the combined output of a concurrent tool batch', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-batch-budget-'))
  const largeRead = buildTool({
    name: 'LargeRead',
    inputSchema: { id: { type: 'number', required: true } },
    maxResultSizeChars: 100_000,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    async call(input) {
      return `head-${input.id}\n${'x'.repeat(15_000)}\ntail-${input.id}`
    },
  })
  const calls = Array.from({ length: 4 }, (_, index) =>
    createToolCall(`large_${index}`, 'LargeRead', { id: index }))
  const model = new ScriptedModel([
    assistantWithToolCalls('read in parallel', calls),
    messages => {
      const results = messages.filter(message => message.role === 'tool')
      assert.equal(results.length, 4)
      assert.equal(results.reduce((sum, message) => sum + message.content.length, 0) <= 16_000, true)
      assert.equal(results.every(message => message.content.includes('head-')), true)
      assert.equal(results.every(message => message.content.includes('tail-')), true)
      return { role: 'assistant', content: 'bounded' }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [largeRead],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('read all records')],
  })

  assert.equal(result.output, 'bounded')
})

test('agent loop bounds each individual tool result', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-result-budget-'))
  const readTool = buildTool({
    name: 'Read',
    inputSchema: { value: { type: 'string', required: true } },
    maxResultSizeChars: 100_000,
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    async call(input) {
      return {
        id: `memory-${input.value}`,
        content: String(input.value).repeat(15_000),
        source: { ref: `session-${input.value}` },
        temporal: { event_time: '2025-01-01' },
      }
    },
  })
  const model = new ScriptedModel([
    assistantWithToolCalls('', [
      createToolCall('read-1', 'Read', { value: 'a' }),
      createToolCall('read-2', 'Read', { value: 'b' }),
    ]),
    messages => {
      const toolResults = messages.filter(message => message.role === 'tool')
      assert.equal(toolResults.length, 2)
      assert.equal(toolResults.every(message => message.content.length <= 4_000), true)
      assert.equal(toolResults.every(message => {
        const parsed = JSON.parse(message.content) as { id?: string; source?: { ref?: string }; content?: string }
        return parsed.id?.startsWith('memory-')
          && parsed.source?.ref?.startsWith('session-')
          && parsed.content?.includes('structured tool result truncated')
      }), true)
      return { role: 'assistant', content: 'done' }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [readTool],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('read both')],
  })

  assert.equal(result.output, 'done')
})

test('agent loop can reserve the final turn for an answer after repeated tool use', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-final-answer-turn-'))
  let executions = 0
  const readTool = buildTool({
    name: 'Read',
    isReadOnly: () => true,
    async call() {
      return `evidence-${++executions}`
    },
  })
  const model = {
    async next(
      messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      if (context.tools.length > 0) {
        return assistantWithToolCalls('', [
          createToolCall(`read-${context.turn}`, 'Read'),
        ])
      }
      assert.equal(messages.some(message =>
        message.role === 'system' && message.content.includes('tool-use budget is exhausted')), true)
      return { role: 'assistant' as const, content: 'final answer from collected evidence' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [readTool],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('keep searching unless required to answer')],
    maxTurns: 3,
    reserveFinalAnswerTurn: true,
  })

  assert.equal(executions, 2)
  assert.equal(result.status, 'completed')
  assert.equal(result.output, 'final answer from collected evidence')
})

test('reserved final answer turn retries one reasoning-only response without tools', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-final-answer-retry-'))
  let calls = 0
  const model = {
    async *stream(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      calls++
      assert.equal(context.tools.length, 0)
      if (calls === 1) yield { type: 'reasoning_delta' as const, text: 'thinking' }
      else yield { type: 'text_delta' as const, text: 'visible answer after retry' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer after reading')],
    maxTurns: 1,
    reserveFinalAnswerTurn: true,
  })

  assert.equal(calls, 2)
  assert.equal(result.status, 'completed')
  assert.equal(result.output, 'visible answer after retry')
})

test('reasoning-only recovery requires an available tool action without exposing reasoning', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-reasoning-tool-recovery-'))
  let calls = 0
  const Read = buildTool({
    name: 'Read',
    isReadOnly: () => true,
    async call() { return 'recovered evidence' },
  })
  const model = {
    async *stream(
      messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      calls++
      if (calls === 1) {
        assert.equal(context.toolChoice, undefined)
        yield { type: 'reasoning_delta' as const, text: 'private stalled reasoning' }
      } else if (calls === 2) {
        assert.equal(context.toolChoice, 'required')
        assert.equal(messages.some(message => message.content.includes('private stalled reasoning')), false)
        yield { type: 'tool_call' as const, call: createToolCall('read-recovery', 'Read') }
      } else {
        yield { type: 'text_delta' as const, text: 'answer from recovered evidence' }
      }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Read],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('read before answering')],
    maxTurns: 4,
  })

  assert.equal(result.output, 'answer from recovered evidence')
  assert.equal(result.messages.some(message => message.content.includes('private stalled reasoning')), false)
  assert.equal(result.events.filter(event => event.type === 'model_empty_response_retry').length, 1)
})

test('empty assistant responses are retried instead of becoming empty completed answers', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-empty-response-recovery-'))
  let calls = 0
  const model = {
    async next() {
      calls++
      return calls === 1
        ? { role: 'assistant' as const, content: '' }
        : { role: 'assistant' as const, content: 'recovered visible answer' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer visibly')],
    maxTurns: 1,
    reserveFinalAnswerTurn: true,
  })

  assert.equal(calls, 2)
  assert.equal(result.output, 'recovered visible answer')
  assert.equal(result.events.some(event =>
    event.type === 'model_empty_response_retry' && event.reason === 'empty'), true)
})

test('tool calls hallucinated outside the exposed turn toolset are not executed', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-hidden-tool-filter-'))
  let calls = 0
  let executions = 0
  const Read = buildTool({
    name: 'Read',
    isReadOnly: () => true,
    async call() {
      executions++
      return 'should not execute'
    },
  })
  const model = {
    async next(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      calls++
      assert.equal(context.tools.length, 0)
      return calls === 1
        ? assistantWithToolCalls('', [createToolCall('hidden-read', 'Read')])
        : { role: 'assistant' as const, content: 'final report' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Read],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('report now')],
    maxTurns: 1,
    reserveFinalAnswerTurn: true,
  })

  assert.equal(executions, 0)
  assert.equal(result.output, 'final report')
})

test('a designated successful tool closes the tool phase and reserves synthesis', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-answer-after-tool-'))
  let toolExecutions = 0
  const Compile = buildTool({
    name: 'Compile',
    isReadOnly: () => true,
    async call() {
      toolExecutions++
      return 'compiled evidence packet'
    },
  })
  const model = {
    async next(
      messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      if (toolExecutions === 0) {
        assert.equal(context.tools.length, 1)
        return assistantWithToolCalls('', [createToolCall('compile-1', 'Compile')])
      }
      assert.equal(context.tools.length, 0)
      assert.equal(messages.some(message =>
        message.role === 'system' && message.content.includes('evidence phase is closed')), true)
      return { role: 'assistant' as const, content: 'final synthesis' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Compile],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('compile then answer')],
    answerAfterToolNames: ['Compile'],
  })

  assert.equal(toolExecutions, 1)
  assert.equal(result.output, 'final synthesis')
})

test('tool lifecycle limits and prerequisites keep orchestration within its phase budget', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-tool-lifecycle-'))
  const executions: string[] = []
  const tool = (name: string) => buildTool({
    name,
    isReadOnly: () => true,
    async call() {
      executions.push(name)
      return `${name} complete`
    },
  })
  const Todo = tool('Todo')
  const Fork = tool('Fork')
  const Compile = tool('Compile')
  let turn = 0
  const model = {
    async next(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      turn++
      const names = context.tools.map(item => item.name)
      if (turn === 1) {
        assert.deepEqual(names, ['Todo', 'Fork'])
        return assistantWithToolCalls('', [createToolCall('todo-1', 'Todo')])
      }
      if (turn === 2) {
        assert.deepEqual(names, ['Fork'])
        return assistantWithToolCalls('', [createToolCall('fork-1', 'Fork')])
      }
      if (turn === 3) {
        assert.deepEqual(names, ['Fork', 'Compile'])
        return assistantWithToolCalls('', [
          createToolCall('fork-2', 'Fork'),
          createToolCall('fork-over-limit', 'Fork'),
        ])
      }
      if (turn === 4) {
        assert.deepEqual(names, ['Compile'])
        return assistantWithToolCalls('', [createToolCall('compile-1', 'Compile')])
      }
      assert.deepEqual(names, [])
      return { role: 'assistant' as const, content: 'bounded final answer' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Todo, Fork, Compile],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('run bounded orchestration')],
    maxToolCallsPerTurn: 3,
    toolCallLimits: { Todo: 1, Fork: 2, Compile: 1 },
    toolPrerequisites: { Compile: ['Fork'] },
    answerAfterToolNames: ['Compile'],
  })

  assert.deepEqual(executions, ['Todo', 'Fork', 'Fork', 'Compile'])
  assert.equal(result.output, 'bounded final answer')
})

test('required evidence gate rejects direct answers until an evidence tool succeeds', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-required-evidence-'))
  const Todo = buildTool({ name: 'Todo', isReadOnly: () => true, async call() { return 'planned' } })
  const Fork = buildTool({ name: 'Fork', isReadOnly: () => true, async call() { return 'sourced evidence' } })
  const Compile = buildTool({ name: 'Compile', isReadOnly: () => true, async call() { return 'compiled' } })
  let turn = 0
  const model = {
    async next(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      turn++
      if (turn === 1) return { role: 'assistant' as const, content: 'unsupported catalog answer' }
      if (turn === 2) {
        assert.equal(context.toolChoice, 'required')
        return assistantWithToolCalls('', [createToolCall('todo-1', 'Todo')])
      }
      if (turn === 3) return { role: 'assistant' as const, content: 'still unsupported' }
      if (turn === 4) {
        assert.equal(context.toolChoice, 'required')
        assert.deepEqual(context.tools.map(tool => tool.name), ['Fork'])
        return assistantWithToolCalls('', [createToolCall('fork-1', 'Fork')])
      }
      return { role: 'assistant' as const, content: 'supported final answer' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Todo, Fork, Compile],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer only after reading evidence')],
    toolCallLimits: { Todo: 1, Fork: 2, Compile: 1 },
    toolPrerequisites: { Compile: ['Fork'] },
    requireAnyToolBeforeAnswer: ['Fork'],
    maxTurns: 6,
  })

  assert.equal(result.output, 'supported final answer')
  assert.equal(result.messages.some(message => message.content === 'unsupported catalog answer'), false)
  assert.equal(result.events.filter(event => event.type === 'model_premature_answer_retry').length, 2)
})

test('one ledger result requires compilation before the answer phase', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-required-compile-'))
  const Fork = buildTool({ name: 'Fork', isReadOnly: () => true, async call() { return 'evidence' } })
  const Compile = buildTool({ name: 'Compile', isReadOnly: () => true, async call() { return 'packet' } })
  let turn = 0
  const model = {
    async next(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      turn++
      if (turn === 1) return assistantWithToolCalls('', [createToolCall('fork-1', 'Fork')])
      if (turn === 2) return { role: 'assistant' as const, content: 'premature synthesis' }
      if (turn === 3) {
        assert.equal(context.toolChoice, 'required')
        assert.deepEqual(context.tools.map(tool => tool.name), ['Compile'])
        return assistantWithToolCalls('', [createToolCall('compile-1', 'Compile')])
      }
      assert.deepEqual(context.tools, [])
      return { role: 'assistant' as const, content: 'compiled final answer' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Fork, Compile],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('compile two reports')],
    toolCallLimits: { Fork: 2, Compile: 1 },
    toolPrerequisites: { Compile: ['Fork'] },
    requireAnyToolBeforeAnswer: ['Fork'],
    requireToolBeforeAnswerAfter: [
      { requiredTool: 'Compile', triggerTool: 'Fork', triggerCount: 1 },
    ],
    answerAfterToolNames: ['Compile'],
    maxTurns: 5,
    reserveFinalAnswerTurn: true,
  })

  assert.equal(result.output, 'compiled final answer')
  assert.equal(result.messages.some(message => message.content === 'premature synthesis'), false)
})

test('a terminal tool on the last planned turn receives a bounded synthesis turn', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-late-terminal-'))
  const Compile = buildTool({ name: 'Compile', isReadOnly: () => true, async call() { return 'packet' } })
  let turn = 0
  const model = {
    async *stream(
      _messages: readonly import('../src/core/messages.js').Message[],
      context: import('../src/core/agent-loop.js').ModelContext,
    ) {
      turn++
      if (turn < 3) {
        yield { type: 'reasoning_delta' as const, text: 'not yet' }
        return
      }
      if (turn === 3) {
        assert.deepEqual(context.tools.map(tool => tool.name), ['Compile'])
        yield { type: 'tool_call' as const, call: createToolCall('compile-late', 'Compile') }
        return
      }
      assert.deepEqual(context.tools, [])
      yield { type: 'text_delta' as const, text: 'late compiled answer' }
    },
  }

  const result = await runAgentLoop({
    model,
    tools: [Compile],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('compile before answering')],
    maxTurns: 1,
    reserveFinalAnswerTurn: true,
    answerAfterToolNames: ['Compile'],
    requireAnyToolBeforeAnswer: ['Compile'],
  })

  assert.equal(result.output, 'late compiled answer')
  assert.equal(turn, 4)
})

test('agent loop defers tool calls beyond the provider batch limit', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-call-budget-'))
  let executions = 0
  const readTool = buildTool({
    name: 'Read',
    inputSchema: { value: { type: 'number', required: true } },
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    async call() {
      return String(++executions)
    },
  })
  const model = new ScriptedModel([
    assistantWithToolCalls('', Array.from({ length: 8 }, (_, index) =>
      createToolCall(`read-${index}`, 'Read', { value: index }))),
    messages => {
      assert.equal(messages.filter(message => message.role === 'tool').length, 4)
      assert.equal(messages.some(message =>
        message.role === 'tool' && message.content.includes('4 additional tool calls were deferred')), true)
      return { role: 'assistant', content: 'done' }
    },
  ])

  const result = await runAgentLoop({
    model,
    tools: [readTool],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('read a bounded batch')],
  })

  assert.equal(executions, 4)
  assert.equal(result.output, 'done')
})

test('agent loop supports a provider-specific serial tool-call limit', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'agent-serial-tool-limit-'))
  let executions = 0
  const readTool = buildTool({
    name: 'Read',
    inputSchema: { value: { type: 'number', required: true } },
    isReadOnly: () => true,
    isConcurrencySafe: () => true,
    async call() {
      executions++
      return 'read'
    },
  })
  const model = new ScriptedModel([
    assistantWithToolCalls('', [
      createToolCall('read-1', 'Read', { value: 1 }),
      createToolCall('read-2', 'Read', { value: 2 }),
    ]),
    { role: 'assistant', content: 'done' },
  ])

  const result = await runAgentLoop({
    model,
    tools: [readTool],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('read serially')],
    maxToolCallsPerTurn: 1,
  })

  assert.equal(executions, 1)
  assert.equal(result.messages.filter(message => message.role === 'tool').length, 1)
  assert.equal(result.output, 'done')
})
