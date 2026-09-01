import assert from 'node:assert/strict'
import { mkdtemp } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { runAgentLoop, type ModelContext } from '../src/core/agent-loop.js'
import {
  canonicalizeToolPairs,
  CompactingContextManager,
  StructuredConversationSummarizer,
} from '../src/core/context-compression.js'
import type { ToolHooks } from '../src/core/hooks.js'
import {
  createAssistantMessage,
  createSystemMessage,
  createToolResultMessage,
  createUserMessage,
  type Message,
} from '../src/core/messages.js'
import { ScriptedModel, assistantWithToolCalls, createToolCall } from '../src/core/mock-model.js'
import { createPermissionContext } from '../src/core/permissions.js'
import { buildTool } from '../src/core/tool.js'
import { createTokenHubStreamingModel } from '../src/adapters/tokenhub-stream.js'
import {
  createOpenAICompatibleStreamRequest,
  toProviderTool,
} from '../src/adapters/openai-compatible-client.js'

test('message canonicalizer drops orphan results and closes incomplete tool batches', () => {
  const canonical = canonicalizeToolPairs([
    createUserMessage('start'),
    createToolResultMessage({ toolCallId: 'orphan', toolName: 'Read', content: 'orphan' }),
    assistantWithToolCalls('tools', [
      createToolCall('read_1', 'Read', { path: 'a' }),
      createToolCall('read_2', 'Read', { path: 'b' }),
    ]),
    createToolResultMessage({ toolCallId: 'read_1', toolName: 'Read', content: 'a' }),
    createUserMessage('continue'),
  ])

  assert.equal(canonical.droppedOrphanToolResults, 1)
  assert.equal(canonical.synthesizedToolResults, 1)
  assert.deepEqual(
    canonical.messages.filter(message => message.role === 'tool').map(message => message.tool_call_id),
    ['read_1', 'read_2'],
  )
  const synthetic = canonical.messages.find(
    message => message.role === 'tool' && message.tool_call_id === 'read_2',
  )
  assert.equal(synthetic?.role, 'tool')
  assert.equal(synthetic?.role === 'tool' ? synthetic.is_error : false, true)
})

test('provider tool schemas preserve objects and declare arrays with item types', () => {
  const tool = buildTool({
    name: 'SchemaProbe',
    inputSchema: {
      source: { type: 'object', required: true },
      tags: { type: 'array', items: { type: 'string' } },
    },
    async call() { return null },
  })
  const provider = toProviderTool(tool) as any

  assert.equal(provider.function.parameters.properties.source.type, 'object')
  assert.equal(provider.function.parameters.properties.tags.type, 'array')
  assert.equal(provider.function.parameters.properties.tags.items.type, 'string')
})

test('OpenAI-compatible requests omit tools and tool_choice when no tools are available', async () => {
  let requestBody: Record<string, unknown> | undefined
  const fetchImpl = (async (_input: string | URL | Request, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>
    return new Response(JSON.stringify({
      choices: [{ message: { content: 'ok' }, finish_reason: 'stop' }],
    }), { headers: { 'content-type': 'application/json' } })
  }) as typeof fetch
  const request = createOpenAICompatibleStreamRequest({
    apiKey: 'test-key',
    baseUrl: 'https://example.test/v1',
    model: 'test-model',
  }, fetchImpl)
  const model = createTokenHubStreamingModel(request)
  const root = await mkdtemp(path.join(os.tmpdir(), 'openai-request-'))

  const result = await runAgentLoop({
    model,
    tools: [],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer')],
  })

  assert.equal(result.output, 'ok')
  assert.equal(Object.hasOwn(requestBody ?? {}, 'tools'), false)
  assert.equal(Object.hasOwn(requestBody ?? {}, 'tool_choice'), false)
})

test('OpenAI-compatible requests forward required tool choice during recovery', async () => {
  let requestBody: Record<string, unknown> | undefined
  const fetchImpl = (async (_input: string | URL | Request, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>
    return new Response(JSON.stringify({
      choices: [{ message: { content: 'ok' }, finish_reason: 'stop' }],
    }), { headers: { 'content-type': 'application/json' } })
  }) as typeof fetch
  const request = createOpenAICompatibleStreamRequest({
    apiKey: 'test-key',
    baseUrl: 'https://example.test/v1',
    model: 'test-model',
  }, fetchImpl)
  const root = await mkdtemp(path.join(os.tmpdir(), 'openai-required-tool-'))
  const Probe = buildTool({ name: 'Probe', async call() { return 'ok' } })
  const permissionContext = createPermissionContext({ cwd: root, readableRoots: [root] })

  for await (const _chunk of request(
    [createUserMessage('act')],
    { tools: [Probe], permissionContext, turn: 2, toolChoice: 'required' },
  )) { /* consume response */ }

  assert.equal(requestBody?.tool_choice, 'required')
})

test('structured working state remains valid JSON under a tiny summary budget', async () => {
  const summary = await StructuredConversationSummarizer.summarize([
    createUserMessage('Remember a very long objective. '.repeat(30)),
    createAssistantMessage('We decided to preserve source provenance. '.repeat(20)),
  ], 180)

  assert.equal(summary.length <= 180, true)
  const body = summary.match(/<working_state[^>]*>\n([\s\S]*)\n<\/working_state>/)?.[1]
  assert.doesNotThrow(() => JSON.parse(body ?? 'invalid'))
})

test('TokenHub adapter never promotes reasoning_content into assistant content', async () => {
  const model = createTokenHubStreamingModel(async function* () {
    yield { choices: [{ delta: { reasoning_content: 'hidden analysis' } }] }
    yield { choices: [{ delta: { content: 'visible ' } }] }
    yield { choices: [{ delta: { content: 'answer' }, finish_reason: 'stop' }] }
  })
  const root = await mkdtemp(path.join(os.tmpdir(), 'tokenhub-stream-'))
  const result = await runAgentLoop({
    model,
    tools: [],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer')],
  })

  assert.equal(result.output, 'visible answer')
  assert.equal(result.messages.some(message => message.content.includes('hidden analysis')), false)
  assert.equal(result.events.some(event => event.type === 'assistant_reasoning_delta'), true)
})

test('reasoning-only stream turns are retried instead of becoming empty final answers', async () => {
  let turn = 0
  const model = createTokenHubStreamingModel(async function* () {
    turn++
    if (turn === 1) {
      yield { choices: [{ delta: { reasoning_content: 'unfinished reasoning' }, finish_reason: 'length' }] }
    } else {
      yield { choices: [{ delta: { content: 'recovered answer' }, finish_reason: 'stop' }] }
    }
  })
  const root = await mkdtemp(path.join(os.tmpdir(), 'reasoning-retry-'))
  const result = await runAgentLoop({
    model,
    tools: [],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('answer after reasoning')],
  })

  assert.equal(result.output, 'recovered answer')
  assert.equal(result.events.some(event => event.type === 'model_empty_response_retry'), true)
})

test('stream adapter separates reasoning, answer text, and partial tool JSON', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'stream-agent-'))
  let turn = 0
  const streamingModel = {
    async *stream() {
      turn++
      if (turn === 1) {
        yield { type: 'reasoning_delta' as const, text: 'private chain of thought' }
        yield { type: 'text_delta' as const, text: 'Calling echo.' }
        yield { type: 'tool_call_start' as const, id: 'echo_1', name: 'Echo' }
        yield { type: 'tool_input_delta' as const, id: 'echo_1', partialJson: '{"value":' }
        yield { type: 'tool_input_delta' as const, id: 'echo_1', partialJson: '"hello"}' }
      } else {
        yield { type: 'reasoning_delta' as const, text: 'still private' }
        yield { type: 'text_delta' as const, text: 'Final visible answer.' }
      }
      yield { type: 'end' as const }
    },
  }
  const Echo = buildTool<{ value: string }, string>({
    name: 'Echo',
    inputSchema: { value: { type: 'string', required: true } },
    isReadOnly: () => true,
    call: async input => input.value,
  })

  const result = await runAgentLoop({
    model: streamingModel,
    tools: [Echo],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('echo hello')],
  })

  assert.equal(result.output, 'Final visible answer.')
  assert.equal(result.messages.some(message => message.content.includes('private chain of thought')), false)
  assert.equal(result.messages.find(message => message.role === 'tool')?.content, 'hello')
  assert.equal(result.events.filter(event => event.type === 'assistant_reasoning_delta').length, 2)
})

test('query stream retries one truncated tool input with a compact required call', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'stream-tool-retry-'))
  let turn = 0
  const toolChoices: Array<string | undefined> = []
  const streamingModel = {
    async *stream(_messages: readonly Message[], context: ModelContext) {
      turn++
      toolChoices.push(context.toolChoice)
      if (turn === 1) {
        yield { type: 'tool_call_start' as const, id: 'echo_bad', name: 'Echo' }
        yield { type: 'tool_input_delta' as const, id: 'echo_bad', partialJson: '{"value":"unfinished' }
      } else if (turn === 2) {
        yield { type: 'tool_call_start' as const, id: 'echo_ok', name: 'Echo' }
        yield { type: 'tool_input_delta' as const, id: 'echo_ok', partialJson: '{"value":"recovered"}' }
      } else {
        yield { type: 'text_delta' as const, text: 'Final after recovered tool call.' }
      }
      yield { type: 'end' as const }
    },
  }
  const Echo = buildTool<{ value: string }, string>({
    name: 'Echo',
    inputSchema: { value: { type: 'string', required: true } },
    isReadOnly: () => true,
    call: async input => input.value,
  })

  const result = await runAgentLoop({
    model: streamingModel,
    tools: [Echo],
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('echo after retry')],
    maxTurns: 4,
  })

  assert.equal(result.output, 'Final after recovered tool call.')
  assert.deepEqual(toolChoices, [undefined, 'required', undefined])
  assert.equal(result.events.filter(event => event.type === 'model_tool_input_retry').length, 1)
  assert.equal(result.messages.some(message => message.content.includes('unfinished')), false)
})

test('pre, post, and error hooks participate in the tool lifecycle', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'hook-agent-'))
  const order: string[] = []
  const Transform = buildTool<{ value: string }, string>({
    name: 'Transform',
    inputSchema: { value: { type: 'string', required: true } },
    isReadOnly: () => true,
    async call(input) {
      order.push(`call:${input.value}`)
      if (input.value === 'recover') throw new Error('planned failure')
      return input.value
    },
  })
  const hooks: ToolHooks = {
    pre: [{
      name: 'normalize',
      async run(context) {
        order.push('pre')
        return {
          updatedInput: { ...context.input, value: String(context.input.value).toUpperCase() },
          additionalContext: 'pre hook normalized the input',
        }
      },
    }],
    post: [{
      name: 'decorate',
      async run(context) {
        order.push('post')
        return { output: `post:${context.output}` }
      },
    }],
  }
  const model = new ScriptedModel([
    assistantWithToolCalls('transform', [createToolCall('transform_1', 'Transform', { value: 'hello' })]),
    messages => ({
      role: 'assistant',
      content: messages.find(message => message.role === 'tool')?.content ?? '',
    }),
  ])

  const result = await runAgentLoop({
    model,
    tools: [Transform],
    hooks,
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('transform')],
  })
  assert.deepEqual(order, ['pre', 'call:HELLO', 'post'])
  assert.equal(result.output, 'post:HELLO')
  assert.equal(result.messages.some(message => message.role === 'system' && message.content.includes('normalized')), true)
})

test('error hooks can recover a failed tool into a normal paired result', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'hook-recovery-'))
  const Failing = buildTool({
    name: 'Failing',
    isReadOnly: () => true,
    async call() { throw new Error('temporary failure') },
  })
  const model = new ScriptedModel([
    assistantWithToolCalls('try', [createToolCall('failure_1', 'Failing')]),
    messages => ({
      role: 'assistant',
      content: messages.find(message => message.role === 'tool')?.content ?? '',
    }),
  ])
  const result = await runAgentLoop({
    model,
    tools: [Failing],
    hooks: {
      error: [{ name: 'fallback', async run() { return { recoveredOutput: 'cached fallback' } } }],
    },
    permissionContext: createPermissionContext({ cwd: root, readableRoots: [root] }),
    messages: [createUserMessage('recover')],
  })
  assert.equal(result.output, 'cached fallback')
  assert.equal(result.messages.find(message => message.role === 'tool')?.is_error, false)
})

test('context compression preserves tool-call and tool-result pairs as one unit', async () => {
  const callMessage = assistantWithToolCalls('old tool call', [createToolCall('read_1', 'Read', { path: 'a' })])
  const resultMessage = createToolResultMessage({
    toolCallId: 'read_1',
    toolName: 'Read',
    content: 'old tool result',
  })
  const messages = [
    createUserMessage('x'.repeat(300)),
    createAssistantMessage('y'.repeat(300)),
    callMessage,
    resultMessage,
    createUserMessage('latest question'),
  ]
  const manager = new CompactingContextManager({
    maxChars: 400,
    preserveRecentChars: 350,
    summaryMaxChars: 200,
  })
  const prepared = await manager.prepare(messages, 1)
  const keptCall = prepared.messages.find(message => message.role === 'assistant' && message.tool_calls?.[0]?.id === 'read_1')
  const keptResult = prepared.messages.find(message => message.role === 'tool' && message.tool_call_id === 'read_1')

  assert.equal(Boolean(keptCall), Boolean(keptResult))
  assert.equal(prepared.metadata?.compacted, true)
  assert.equal(prepared.messages.at(-1)?.content, 'latest question')
})

test('context compression enforces the final budget after delegated memory injection', async () => {
  const manager = new CompactingContextManager({
    maxChars: 1_200,
    preserveRecentChars: 400,
    summaryMaxChars: 250,
    delegate: {
      async prepare(messages) {
        return {
          messages: [
            { role: 'system', content: `<memory_context>${'evidence '.repeat(180)}</memory_context>` },
            ...messages,
          ],
          metadata: { memoryHits: 4 },
        }
      },
    },
  })
  const prepared = await manager.prepare([
    createUserMessage('old question '.repeat(40)),
    createAssistantMessage('old answer '.repeat(40)),
    createUserMessage('latest question'),
  ], 1)
  const finalChars = prepared.messages.reduce((sum, message) => sum + JSON.stringify(message).length, 0)

  assert.equal(prepared.metadata?.postInjectionCompacted, true)
  assert.equal(prepared.metadata?.contextCharsAfterInjection as number > 1_200, true)
  assert.equal(finalChars <= 1_200, true)
  assert.equal(prepared.metadata?.contextCharsAfter, finalChars)
})

test('context compression always preserves the latest user role across tool rounds', async () => {
  const manager = new CompactingContextManager({
    maxChars: 6_000,
    preserveRecentChars: 3_500,
    summaryMaxChars: 1_500,
  })
  const firstCall = assistantWithToolCalls('', [createToolCall('read_1', 'Read', { id: 'one' })])
  const secondCall = assistantWithToolCalls('', [createToolCall('read_2', 'Read', { id: 'two' })])
  const prepared = await manager.prepare([
    createSystemMessage('system'),
    createUserMessage(`latest request ${'q'.repeat(2_000)}`),
    firstCall,
    createToolResultMessage({ toolCallId: 'read_1', toolName: 'Read', content: 'a'.repeat(4_000) }),
    secondCall,
    createToolResultMessage({ toolCallId: 'read_2', toolName: 'Read', content: 'b'.repeat(4_000) }),
  ], 2)
  const finalChars = prepared.messages.reduce((sum, message) => sum + JSON.stringify(message).length, 0)

  assert.equal(prepared.metadata?.compacted, true)
  assert.equal(prepared.messages.some(message => message.role === 'user'), true)
  assert.equal(finalChars <= 6_000, true)
})
