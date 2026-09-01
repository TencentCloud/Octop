import type { Message } from '../core/messages.js'
import type { ModelContext } from '../core/agent-loop.js'
import type { Tool } from '../core/tool.js'
import { PermissionBehavior } from '../core/permissions.js'
import type { TokenHubChunk, TokenHubStreamRequest } from './tokenhub-stream.js'
import { canonicalizeToolPairs } from '../core/context-compression.js'

export type OpenAICompatibleStreamConfig = {
  apiKey: string
  baseUrl: string
  model: string
  maxTokens?: number
  temperature?: number
  timeoutMs?: number
}

export function createOpenAICompatibleStreamRequest(
  config: OpenAICompatibleStreamConfig,
  fetchImpl: typeof fetch = globalThis.fetch,
): TokenHubStreamRequest {
  if (!config.apiKey) throw new Error('OpenAI-compatible stream requires an API key')
  return async function* request(messages, context) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), config.timeoutMs ?? 120_000)
    try {
      const tools = context.tools
        .filter(tool => context.permissionContext.toolRules[tool.name] !== PermissionBehavior.DENY)
        .map(toProviderTool)
      const providerMessages = canonicalizeToolPairs(messages).messages.map(toProviderMessage)
      const response = await fetchImpl(`${trimTrailingSlash(config.baseUrl)}/chat/completions`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${config.apiKey}`,
          'content-type': 'application/json',
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: config.model,
          messages: providerMessages,
          ...(tools.length > 0 ? { tools, tool_choice: context.toolChoice ?? 'auto' } : {}),
          stream: true,
          temperature: config.temperature ?? 0,
          max_tokens: config.maxTokens ?? 2_048,
        }),
      })
      if (!response.ok) {
        const text = await response.text()
        throw new Error([
          `model request failed: HTTP ${response.status} ${text.slice(0, 300)}`,
          `request_shape=${JSON.stringify(summarizeRequestShape(providerMessages, tools.length))}`,
        ].join(' '))
      }
      if (!response.body) throw new Error('model stream response has no body')

      const contentType = response.headers.get('content-type') ?? ''
      if (contentType.includes('application/json')) {
        yield completionToChunk(await response.json())
        return
      }
      yield* parseServerSentEvents(response.body)
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        throw new Error(`model request timed out after ${config.timeoutMs ?? 120_000}ms`)
      }
      throw error
    } finally {
      clearTimeout(timeout)
    }
  }
}

function summarizeRequestShape(messages: Record<string, unknown>[], toolCount: number) {
  return {
    message_count: messages.length,
    total_chars: JSON.stringify(messages).length,
    tool_count: toolCount,
    messages: messages.map(message => ({
      role: message.role,
      content_chars: typeof message.content === 'string' ? message.content.length : 0,
      tool_call_count: Array.isArray(message.tool_calls) ? message.tool_calls.length : 0,
      tool_call_id: typeof message.tool_call_id === 'string' ? message.tool_call_id : undefined,
    })),
  }
}

export function toProviderMessage(message: Message): Record<string, unknown> {
  if (message.role === 'tool') {
    return { role: 'tool', tool_call_id: message.tool_call_id, content: message.content }
  }
  if (message.role === 'assistant' && message.tool_calls?.length) {
    return {
      role: 'assistant',
      content: message.content || null,
      tool_calls: message.tool_calls.map(call => ({
        id: call.id,
        type: 'function',
        function: { name: call.name, arguments: JSON.stringify(call.input ?? {}) },
      })),
    }
  }
  return { role: message.role, content: message.content }
}

export function toProviderTool(tool: Tool): Record<string, unknown> {
  return {
    type: 'function',
    function: {
      name: tool.name,
      description: tool.description,
      parameters: {
        type: 'object',
        properties: Object.fromEntries(Object.entries(tool.inputSchema).map(([name, field]) => [
          name,
          toProviderInputField(field),
        ])),
        required: Object.entries(tool.inputSchema)
          .filter(([, field]) => field.required)
          .map(([name]) => name),
        additionalProperties: true,
      },
    },
  }
}

function toProviderInputField(field: import('../core/tool.js').ToolInputField): Record<string, unknown> {
  return {
    type: field.type ?? 'string',
    ...(field.items ? { items: toProviderInputField(field.items) } : {}),
    ...(field.properties ? {
      properties: Object.fromEntries(Object.entries(field.properties).map(([name, nested]) => [
        name,
        toProviderInputField(nested),
      ])),
      required: Object.entries(field.properties)
        .filter(([, nested]) => nested.required)
        .map(([name]) => name),
    } : {}),
    ...(field.additionalProperties !== undefined ? { additionalProperties: field.additionalProperties } : {}),
    ...(field.minimum !== undefined ? { minimum: field.minimum } : {}),
    ...(field.maximum !== undefined ? { maximum: field.maximum } : {}),
  }
}

async function* parseServerSentEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<TokenHubChunk> {
  const decoder = new TextDecoder()
  let buffer = ''
  for await (const bytes of body) {
    buffer += decoder.decode(bytes, { stream: true })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const data = trimmed.slice(5).trim()
      if (!data || data === '[DONE]') continue
      yield JSON.parse(data) as TokenHubChunk
    }
  }
  buffer += decoder.decode()
  const tail = buffer.trim()
  if (tail.startsWith('data:')) {
    const data = tail.slice(5).trim()
    if (data && data !== '[DONE]') yield JSON.parse(data) as TokenHubChunk
  }
}

function completionToChunk(data: any): TokenHubChunk {
  const choice = data?.choices?.[0] ?? {}
  const message = choice.message ?? {}
  return {
    choices: [{
      delta: {
        content: message.content ?? null,
        reasoning_content: message.reasoning_content ?? null,
        tool_calls: message.tool_calls?.map((call: any, index: number) => ({
          index,
          id: call.id,
          function: call.function,
        })),
      },
      finish_reason: choice.finish_reason,
    }],
  }
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}
