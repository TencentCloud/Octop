import {
  executeToolCall,
  truncateToolResultContent,
  type ExecuteToolCallResult,
} from './tool-execution.js'
import {
  findToolByName,
  validateToolInput,
  type Tool,
} from './tool.js'
import type { PermissionContext } from './permissions.js'
import type {
  AgentEvent,
  Message,
  ToolCall,
  ToolResultMessage,
  SystemMessage,
} from './messages.js'
import type { ToolHooks } from './hooks.js'

export type RunToolCallsParams = {
  toolCalls: readonly ToolCall[]
  tools: readonly Tool[]
  permissionContext: PermissionContext
  messages: readonly Message[]
  turn: number
  hooks?: ToolHooks
}

export type RunToolCallsResult = {
  messages: ToolResultMessage[]
  events: AgentEvent[]
  contextMessages: SystemMessage[]
}

const MAX_TOOL_BATCH_RESULT_CHARS = 16_000
const MAX_SINGLE_TOOL_RESULT_CHARS = 4_000

type ToolCallBatch = {
  mode: 'concurrent' | 'serial'
  calls: ToolCall[]
}

function canRunConcurrently(toolCall: ToolCall, tools: readonly Tool[]): boolean {
  const tool = findToolByName(tools, toolCall.name)
  if (!tool) return false

  try {
    const input = validateToolInput(tool, toolCall.input ?? {})
    return tool.isConcurrencySafe(input)
  } catch {
    return false
  }
}

export function createToolCallBatches(
  toolCalls: readonly ToolCall[],
  tools: readonly Tool[],
): ToolCallBatch[] {
  const batches: ToolCallBatch[] = []
  let pendingConcurrent: ToolCall[] = []

  const flushConcurrent = () => {
    if (pendingConcurrent.length === 0) return
    batches.push({ mode: 'concurrent', calls: pendingConcurrent })
    pendingConcurrent = []
  }

  for (const toolCall of toolCalls) {
    if (canRunConcurrently(toolCall, tools)) {
      pendingConcurrent.push(toolCall)
      continue
    }

    flushConcurrent()
    batches.push({ mode: 'serial', calls: [toolCall] })
  }

  flushConcurrent()
  return batches
}

export async function runToolCalls({
  toolCalls,
  tools,
  permissionContext,
  messages,
  turn,
  hooks,
}: RunToolCallsParams): Promise<RunToolCallsResult> {
  const workingMessages: Message[] = [...messages]
  const toolMessages: ToolResultMessage[] = []
  const events: AgentEvent[] = []
  const contextMessages: SystemMessage[] = []

  for (const batch of createToolCallBatches(toolCalls, tools)) {
    if (batch.mode === 'concurrent') {
      const snapshot = [...workingMessages]
      const results = await Promise.all(
        batch.calls.map(toolCall =>
          executeToolCall({
            toolCall,
            tools,
            permissionContext,
            messages: snapshot,
            turn,
            hooks,
          }),
        ),
      )
      appendResults(results, workingMessages, toolMessages, contextMessages, events)
      continue
    }

    for (const toolCall of batch.calls) {
      const result = await executeToolCall({
        toolCall,
        tools,
        permissionContext,
        messages: workingMessages,
        turn,
        hooks,
      })
      appendResults([result], workingMessages, toolMessages, contextMessages, events)
    }
  }

  boundToolResultBatch(toolMessages, MAX_TOOL_BATCH_RESULT_CHARS)
  return { messages: toolMessages, events, contextMessages }
}

function boundToolResultBatch(messages: ToolResultMessage[], maxChars: number) {
  const perMessage = Math.max(
    256,
    Math.min(MAX_SINGLE_TOOL_RESULT_CHARS, Math.floor(maxChars / Math.max(1, messages.length))),
  )
  for (const message of messages) {
    if (message.content.length <= perMessage) continue
    message.content = truncateToolResultContent(message.content, perMessage, true)
  }
}

function appendResults(
  results: readonly ExecuteToolCallResult[],
  workingMessages: Message[],
  toolMessages: ToolResultMessage[],
  contextMessages: SystemMessage[],
  events: AgentEvent[],
) {
  for (const result of results) {
    workingMessages.push(result.message)
    toolMessages.push(result.message)
    workingMessages.push(...result.contextMessages)
    contextMessages.push(...result.contextMessages)
    events.push(...result.events)
  }
}
