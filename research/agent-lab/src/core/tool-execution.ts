import {
  PermissionBehavior,
  resolveToolPermission,
  type PermissionContext,
} from './permissions.js'
import {
  createToolResultMessage,
  type AgentEvent,
  type Message,
  type ToolCall,
  type ToolInput,
  type ToolResultMessage,
  type SystemMessage,
  createSystemMessage,
} from './messages.js'
import type { ToolHooks, ToolHookContext } from './hooks.js'
import {
  findToolByName,
  validateToolInput,
  ToolInputError,
  type Tool,
} from './tool.js'

export type ExecuteToolCallParams = {
  toolCall: ToolCall
  tools: readonly Tool[]
  permissionContext: PermissionContext
  messages: readonly Message[]
  turn: number
  hooks?: ToolHooks
}

export type ExecuteToolCallResult = {
  message: ToolResultMessage
  events: AgentEvent[]
  contextMessages: SystemMessage[]
}

export function formatToolOutput(output: unknown, maxResultSizeChars: number): string {
  const content =
    typeof output === 'string'
      ? output
      : JSON.stringify(output, null, 2) ?? String(output)

  return truncateToolResultContent(content, maxResultSizeChars)
}

export function truncateToolResultContent(
  content: string,
  maxChars: number,
  preserveTail = false,
): string {
  if (content.length <= maxChars) return content

  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && maxChars >= 256) {
      return truncateStructuredToolResult(parsed, content.length, maxChars)
    }
  } catch {
    // Plain-text tool results retain the existing prefix truncation contract.
  }

  if (preserveTail) return clipTextHeadTail(content, maxChars, content.length)
  const omitted = content.length - maxChars
  return `${content.slice(0, maxChars)}\n[truncated: ${omitted} chars omitted]`
}

function truncateStructuredToolResult(
  parsed: Record<string, unknown>,
  originalChars: number,
  maxChars: number,
): string {
  const sourceText = typeof parsed.content === 'string'
    ? parsed.content
    : JSON.stringify(parsed)
  const payload: Record<string, unknown> = {
    ...(typeof parsed.id === 'string' ? { id: parsed.id } : {}),
    ...(typeof parsed.kind === 'string' ? { kind: parsed.kind } : {}),
    ...(typeof parsed.title === 'string' ? { title: parsed.title } : {}),
    ...(typeof parsed.summary === 'string' ? { summary: parsed.summary.slice(0, 800) } : {}),
    ...(parsed.source && typeof parsed.source === 'object' ? { source: parsed.source } : {}),
    ...(Array.isArray(parsed.source_refs) ? { source_refs: parsed.source_refs } : {}),
    ...(parsed.temporal && typeof parsed.temporal === 'object' ? { temporal: parsed.temporal } : {}),
    truncated: true,
    original_chars: originalChars,
    content: '',
  }

  let low = 0
  let high = sourceText.length
  let best = JSON.stringify(payload)
  while (low <= high) {
    const length = Math.floor((low + high) / 2)
    payload.content = clipTextHeadTail(sourceText, length, originalChars)
    const candidate = JSON.stringify(payload)
    if (candidate.length <= maxChars) {
      best = candidate
      low = length + 1
    } else {
      high = length - 1
    }
  }
  return best
}

function clipTextHeadTail(content: string, maxChars: number, originalChars: number): string {
  if (content.length <= maxChars) return content
  const marker = `\n[structured tool result truncated; original chars: ${originalChars}]\n`
  if (maxChars <= marker.length) return marker.slice(0, maxChars)
  const available = maxChars - marker.length
  const headChars = Math.ceil(available * 0.65)
  return `${content.slice(0, headChars)}${marker}${content.slice(-(available - headChars))}`
}

function createToolErrorResult({
  toolCall,
  toolName,
  turn,
  content,
}: {
  toolCall: ToolCall
  toolName: string
  turn: number
  content: string
}): ExecuteToolCallResult {
  const message = createToolResultMessage({
    toolCallId: toolCall.id,
    toolName,
    isError: true,
    content,
  })

  return {
    message,
    events: [{ type: 'tool_error', turn, toolName, error: content }],
    contextMessages: [],
  }
}

export async function executeToolCall({
  toolCall,
  tools,
  permissionContext,
  messages,
  turn,
  hooks,
}: ExecuteToolCallParams): Promise<ExecuteToolCallResult> {
  const toolName = toolCall.name
  const tool = findToolByName(tools, toolName)

  if (!tool) {
    return createToolErrorResult({
      toolCall,
      toolName,
      turn,
      content: `No such tool: ${toolName}`,
    })
  }

  let input: ToolInput
  try {
    input = validateToolInput(tool, toolCall.input ?? {})
  } catch (error) {
    if (!(error instanceof ToolInputError)) throw error
    return createToolErrorResult({
      toolCall,
      toolName,
      turn,
      content: error.message,
    })
  }

  const toolValidation = await tool.validateInput(input, {
    messages: [...messages],
    permissionContext,
  })
  if (!toolValidation.result) {
    return createToolErrorResult({
      toolCall,
      toolName,
      turn,
      content: toolValidation.message,
    })
  }

  const events: AgentEvent[] = []
  const contextMessages: SystemMessage[] = []
  let finalInput = input
  const baseHookContext = (): ToolHookContext => ({
    toolCall,
    tool,
    input: finalInput,
    messages,
    permissionContext,
    turn,
  })

  try {
    for (const hook of hooks?.pre ?? []) {
      events.push({ type: 'hook_start', turn, hook: hook.name, phase: 'pre', toolName })
      const result = await hook.run(baseHookContext())
      events.push({ type: 'hook_end', turn, hook: hook.name, phase: 'pre', toolName })
      if (result?.updatedInput) finalInput = result.updatedInput
      if (result?.additionalContext) contextMessages.push(createSystemMessage(result.additionalContext))
      if (result?.behavior === 'deny') {
        const content = result.message ?? `Pre-tool hook ${hook.name} denied ${toolName}`
        return {
          message: createToolResultMessage({ toolCallId: toolCall.id, toolName, isError: true, content }),
          events: [...events, { type: 'tool_error', turn, toolName, error: content }],
          contextMessages,
        }
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return {
      message: createToolResultMessage({
        toolCallId: toolCall.id,
        toolName,
        isError: true,
        content: `Pre-tool hook failed: ${message}`,
      }),
      events: [...events, { type: 'tool_error', turn, toolName, error: message }],
      contextMessages,
    }
  }

  try {
    finalInput = validateToolInput(tool, finalInput)
    const rewrittenValidation = await tool.validateInput(finalInput, {
      messages: [...messages],
      permissionContext,
    })
    if (!rewrittenValidation.result) {
      return {
        message: createToolResultMessage({
          toolCallId: toolCall.id,
          toolName,
          isError: true,
          content: rewrittenValidation.message,
        }),
        events: [...events, { type: 'tool_error', turn, toolName, error: rewrittenValidation.message }],
        contextMessages,
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return {
      message: createToolResultMessage({ toolCallId: toolCall.id, toolName, isError: true, content: message }),
      events: [...events, { type: 'tool_error', turn, toolName, error: message }],
      contextMessages,
    }
  }

  const permission = await resolveToolPermission(tool, finalInput, permissionContext)
  if (permission.behavior !== PermissionBehavior.ALLOW) {
    const message = createToolResultMessage({
      toolCallId: toolCall.id,
      toolName,
      isError: true,
      content: permission.message ?? `Permission ${permission.behavior}`,
    })

    return {
      message,
      contextMessages,
      events: [
        ...events,
        {
          type: 'tool_permission_denied',
          turn,
          toolName,
          behavior: permission.behavior,
          reason: permission.decisionReason,
        },
      ],
    }
  }

  finalInput = permission.updatedInput ?? finalInput
  events.push({ type: 'tool_call_start', turn, toolName, input: finalInput })

  try {
    let output = await tool.call(finalInput, {
      messages: [...messages],
      permissionContext,
      turn,
      emitEvent: event => events.push(event),
    })
    for (const hook of hooks?.post ?? []) {
      events.push({ type: 'hook_start', turn, hook: hook.name, phase: 'post', toolName })
      const result = await hook.run({ ...baseHookContext(), input: finalInput, output })
      events.push({ type: 'hook_end', turn, hook: hook.name, phase: 'post', toolName })
      if (result && 'output' in result) output = result.output
      if (result?.additionalContext) contextMessages.push(createSystemMessage(result.additionalContext))
    }
    const content = formatToolOutput(output, tool.maxResultSizeChars)
    const message = createToolResultMessage({
      toolCallId: toolCall.id,
      toolName,
      content,
    })

    events.push({ type: 'tool_call_end', turn, toolName, output })
    return { message, events, contextMessages }
  } catch (error) {
    const caughtError = error instanceof Error ? error : new Error(String(error))
    let recovered = false
    let recoveredOutput: unknown
    try {
      for (const hook of hooks?.error ?? []) {
        events.push({ type: 'hook_start', turn, hook: hook.name, phase: 'error', toolName })
        const result = await hook.run({ ...baseHookContext(), input: finalInput, error: caughtError })
        events.push({ type: 'hook_end', turn, hook: hook.name, phase: 'error', toolName })
        if (result && 'recoveredOutput' in result) {
          recovered = true
          recoveredOutput = result.recoveredOutput
        }
        if (result?.additionalContext) contextMessages.push(createSystemMessage(result.additionalContext))
      }
    } catch (hookError) {
      const hookMessage = hookError instanceof Error ? hookError.message : String(hookError)
      caughtError.message += `; error hook failed: ${hookMessage}`
    }

    if (recovered) {
      const content = formatToolOutput(recoveredOutput, tool.maxResultSizeChars)
      events.push({ type: 'tool_call_end', turn, toolName, output: recoveredOutput })
      return {
        message: createToolResultMessage({ toolCallId: toolCall.id, toolName, content }),
        events,
        contextMessages,
      }
    }

    const errorMessage = caughtError.message
    return {
      message: createToolResultMessage({
        toolCallId: toolCall.id,
        toolName,
        isError: true,
        content: `Tool execution failed: ${errorMessage}`,
      }),
      events: [
        ...events,
        {
          type: 'tool_error',
          turn,
          toolName,
          error: `Tool execution failed: ${errorMessage}`,
        },
      ],
      contextMessages,
    }
  }
}
