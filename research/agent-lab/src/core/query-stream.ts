import {
  AssistantStreamAssembler,
  InvalidStreamedToolInputError,
  isStreamingAgentModel,
  type AgentModelLike,
} from './model-stream.js'
import {
  PassthroughContextManager,
  type ContextManager,
} from './context-manager.js'
import { createSystemMessage, type AgentEvent, type AssistantMessage, type Message, type ToolCall } from './messages.js'
import type { PermissionContext } from './permissions.js'
import type { Tool } from './tool.js'
import { runToolCalls } from './tool-orchestration.js'
import type { ToolHooks } from './hooks.js'

export type QueryStreamParams = {
  model: AgentModelLike
  tools: readonly Tool[]
  permissionContext: PermissionContext
  messages: readonly Message[]
  contextManager?: ContextManager
  maxTurns?: number
  maxToolCallsPerTurn?: number
  reserveFinalAnswerTurn?: boolean
  answerAfterToolNames?: readonly string[]
  toolCallLimits?: Readonly<Record<string, number>>
  toolPrerequisites?: Readonly<Record<string, readonly string[]>>
  requireAnyToolBeforeAnswer?: readonly string[]
  requireToolBeforeAnswerAfter?: readonly {
    requiredTool: string
    triggerTool: string
    triggerCount: number
  }[]
  hooks?: ToolHooks
}

export type QueryStreamResult = {
  status: 'completed' | 'max_turns_exceeded'
  messages: Message[]
  output: string | null
}

/**
 * Claude-style query stream: model output is collected, tool calls are
 * orchestrated, and every tool result is paired back into the next model turn.
 */
export async function* runQueryStream({
  model,
  tools,
  permissionContext,
  messages,
  contextManager = PassthroughContextManager,
  maxTurns = 10,
  maxToolCallsPerTurn = 4,
  reserveFinalAnswerTurn = false,
  answerAfterToolNames = [],
  toolCallLimits = {},
  toolPrerequisites = {},
  requireAnyToolBeforeAnswer = [],
  requireToolBeforeAnswerAfter = [],
  hooks,
}: QueryStreamParams): AsyncGenerator<AgentEvent, QueryStreamResult> {
  const currentMessages = [...messages]
  let hardMaxTurns = maxTurns + (reserveFinalAnswerTurn ? 2 : 0)
  const absoluteMaxTurns = maxTurns + (reserveFinalAnswerTurn ? 6 : 0)
  const answerAfterTools = new Set(answerAfterToolNames)
  const successfulToolCounts = new Map<string, number>()
  let answerOnly = false
  let forceAction = false
  let malformedToolInputRetries = 0

  for (let turn = 1; turn <= hardMaxTurns; turn++) {
    const missingAnswerTools = answerGateMissingTools(
      successfulToolCounts,
      requireAnyToolBeforeAnswer,
      requireToolBeforeAnswerAfter,
    )
    const requiredEvidenceReady = missingAnswerTools.length === 0
    const isReservedFinalTurn = reserveFinalAnswerTurn && turn >= maxTurns && requiredEvidenceReady
    if (isReservedFinalTurn && turn === maxTurns) {
      currentMessages.push(createSystemMessage(
        'The tool-use budget is exhausted. Do not request another tool. Answer the original question now using the evidence already collected. If a required fact is unsupported, say that it is not available.',
      ))
    }
    yield { type: 'model_turn_start', turn }
    const prepared = await contextManager.prepare(currentMessages, turn)
    if (prepared.metadata) {
      yield { type: 'context_prepared', turn, metadata: prepared.metadata }
    }
    const eligibleTools = tools.filter(tool => toolIsEligible(
      tool.name,
      successfulToolCounts,
      toolCallLimits,
      toolPrerequisites,
    ))
    const requiredRecoveryTools = new Set(missingAnswerTools)
    const turnTools: Tool[] = isReservedFinalTurn || answerOnly
      ? []
      : forceAction && requiredRecoveryTools.size > 0
        ? eligibleTools.filter(tool => requiredRecoveryTools.has(tool.name))
        : eligibleTools
    const modelContext = {
      tools: turnTools,
      permissionContext,
      turn,
      ...(forceAction && turnTools.length > 0 ? { toolChoice: 'required' as const } : {}),
    }
    let assistant: AssistantMessage
    let reasoningDeltaCount = 0
    if (isStreamingAgentModel(model)) {
      const assembler = new AssistantStreamAssembler()
      yield { type: 'model_stream_start', turn }
      for await (const event of model.stream(prepared.messages, modelContext)) {
        assembler.consume(event)
        if (event.type === 'text_delta') {
          yield { type: 'assistant_text_delta', turn, text: event.text }
        } else if (event.type === 'reasoning_delta') {
          reasoningDeltaCount++
          yield { type: 'assistant_reasoning_delta', turn, text: event.text }
        } else if (event.type === 'tool_input_delta') {
          yield { type: 'tool_input_delta', turn, toolCallId: event.id, partialJson: event.partialJson }
        }
      }
      try {
        assistant = assembler.finish()
      } catch (error) {
        if (!(error instanceof InvalidStreamedToolInputError) || malformedToolInputRetries >= 2) throw error
        malformedToolInputRetries++
        forceAction = turnTools.length > 0
        hardMaxTurns = Math.min(absoluteMaxTurns, Math.max(hardMaxTurns, turn + 2))
        replaceReasoningRecoveryMessage(currentMessages, createSystemMessage(
          `The previous streamed ${error.toolName} call ended with incomplete JSON and was discarded. Retry the same necessary action now with one compact valid JSON object. Keep descriptions and prompts brief; do not repeat analysis before the tool call.`,
        ))
        yield {
          type: 'model_tool_input_retry',
          turn,
          toolName: error.toolName,
          error: error.message,
        }
        continue
      }
      yield { type: 'model_stream_end', turn }
    } else {
      assistant = await model.next(prepared.messages, modelContext)
    }

    assertAssistantMessage(assistant, turn, currentMessages)
    const exposedToolNames = new Set(turnTools.map(tool => tool.name))
    assistant = {
      ...assistant,
      tool_calls: assistant.tool_calls?.filter(call => exposedToolNames.has(call.name)),
    }
    const requestedToolCallCount = assistant.tool_calls?.length ?? 0
    if (requestedToolCallCount > maxToolCallsPerTurn) {
      assistant = {
        ...assistant,
        tool_calls: assistant.tool_calls?.slice(0, maxToolCallsPerTurn),
      }
    }
    assistant = {
      ...assistant,
      tool_calls: boundToolCallsByLifecycle(
        assistant.tool_calls ?? [],
        successfulToolCounts,
        toolCallLimits,
      ),
    }
    yield { type: 'assistant_message', turn, message: assistant }

    const toolCalls = assistant.tool_calls ?? []
    if (toolCalls.length === 0 && !assistant.content.trim()) {
      forceAction = turnTools.length > 0
      replaceReasoningRecoveryMessage(currentMessages, createSystemMessage(
        turnTools.length > 0
          ? 'The previous request produced no usable action. On the next turn, immediately call one available tool that advances the task. Do not repeat the analysis before the tool call.'
          : 'The previous request produced no visible answer. On the next turn, answer directly in at most 200 words using only the evidence already available. Do not repeat the analysis.',
      ))
      yield {
        type: 'model_empty_response_retry',
        turn,
        reason: reasoningDeltaCount > 0 ? 'reasoning_only' : 'empty',
      }
      continue
    }
    if (toolCalls.length === 0 && assistant.content.trim() && !requiredEvidenceReady) {
      forceAction = turnTools.length > 0
      replacePrematureAnswerMessage(currentMessages, createSystemMessage(
        `A final answer is not allowed until the required evidence phase succeeds: ${missingAnswerTools.join(', ')}. The prior response relied on incomplete orchestration or unsupported inference. Immediately perform the required evidence action; do not repeat or defend the premature answer.`,
      ))
      yield {
        type: 'model_premature_answer_retry',
        turn,
        requiredTools: missingAnswerTools,
      }
      continue
    }
    currentMessages.push(assistant)
    forceAction = false
    if (toolCalls.length === 0) {
      yield { type: 'done', turn, message: assistant }
      return {
        status: 'completed',
        messages: currentMessages,
        output: assistant.content,
      }
    }

    const toolRun = await runToolCalls({
      toolCalls,
      tools,
      permissionContext,
      messages: currentMessages,
      turn,
      hooks,
    })
    if (requestedToolCallCount > toolCalls.length) {
      const lastResult = toolRun.messages.at(-1)
      if (lastResult) {
        lastResult.content = appendDeferredToolCallNotice(
          lastResult.content,
          requestedToolCallCount - toolCalls.length,
        )
      }
    }
    currentMessages.push(...toolRun.messages, ...toolRun.contextMessages)
    for (const event of toolRun.events) yield event
    for (const message of toolRun.messages) {
      if (message.is_error) continue
      successfulToolCounts.set(
        message.tool_name,
        (successfulToolCounts.get(message.tool_name) ?? 0) + 1,
      )
    }
    const missingAfterTools = answerGateMissingTools(
      successfulToolCounts,
      requireAnyToolBeforeAnswer,
      requireToolBeforeAnswerAfter,
    )
    if (missingAfterTools.length > 0) {
      hardMaxTurns = Math.min(absoluteMaxTurns, Math.max(hardMaxTurns, turn + 2))
    }
    if (toolRun.messages.some(message =>
      !message.is_error && answerAfterTools.has(message.tool_name),
    )) {
      answerOnly = true
      hardMaxTurns = Math.min(absoluteMaxTurns, Math.max(hardMaxTurns, turn + 2))
      currentMessages.push(createSystemMessage(
        'The designated evidence compilation tool completed successfully. The evidence phase is closed. Do not request more tools; answer the original question directly and concisely from the compiled result. Lead with the best-supported answer, then state material uncertainty without withdrawing that answer.',
      ))
    }
  }

  return {
    status: 'max_turns_exceeded',
    messages: currentMessages,
    output: null,
  }
}

function toolIsEligible(
  toolName: string,
  successfulCounts: ReadonlyMap<string, number>,
  limits: Readonly<Record<string, number>>,
  prerequisites: Readonly<Record<string, readonly string[]>>,
): boolean {
  const limit = limits[toolName]
  if (limit !== undefined && (successfulCounts.get(toolName) ?? 0) >= limit) return false
  return (prerequisites[toolName] ?? []).every(required =>
    (successfulCounts.get(required) ?? 0) > 0,
  )
}

function answerGateMissingTools(
  successfulCounts: ReadonlyMap<string, number>,
  requireAny: readonly string[],
  conditionalRequirements: readonly {
    requiredTool: string
    triggerTool: string
    triggerCount: number
  }[],
): string[] {
  const missing = requireAny.length > 0 && !requireAny.some(name =>
    (successfulCounts.get(name) ?? 0) > 0,
  ) ? [...requireAny] : []
  for (const requirement of conditionalRequirements) {
    if (
      (successfulCounts.get(requirement.triggerTool) ?? 0) >= requirement.triggerCount &&
      (successfulCounts.get(requirement.requiredTool) ?? 0) === 0
    ) {
      missing.push(requirement.requiredTool)
    }
  }
  return [...new Set(missing)]
}

function boundToolCallsByLifecycle(
  calls: readonly ToolCall[],
  successfulCounts: ReadonlyMap<string, number>,
  limits: Readonly<Record<string, number>>,
): ToolCall[] {
  const accepted: ToolCall[] = []
  const pendingCounts = new Map<string, number>()
  for (const call of calls) {
    const limit = limits[call.name]
    const used = (successfulCounts.get(call.name) ?? 0) + (pendingCounts.get(call.name) ?? 0)
    if (limit !== undefined && used >= limit) continue
    accepted.push(call)
    pendingCounts.set(call.name, (pendingCounts.get(call.name) ?? 0) + 1)
  }
  return accepted
}

function replaceReasoningRecoveryMessage(messages: Message[], recovery: Message): void {
  const previous = messages.at(-1)
  if (
    previous?.role === 'system' &&
    previous.content.startsWith('The previous request produced no')
  ) {
    messages.pop()
  }
  messages.push(recovery)
}

function replacePrematureAnswerMessage(messages: Message[], recovery: Message): void {
  const previous = messages.at(-1)
  if (
    previous?.role === 'system' &&
    previous.content.startsWith('A final answer is not allowed until one required evidence tool succeeds')
  ) {
    messages.pop()
  }
  messages.push(recovery)
}

function appendDeferredToolCallNotice(content: string, count: number): string {
  const message = `${count} additional tool calls were deferred to keep this turn within the provider batch limit. Request them in the next turn if still needed.`
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return JSON.stringify({ ...parsed, deferred_tool_calls: { count, message } })
    }
  } catch {
    // Plain text remains plain text.
  }
  return `${content}\n[${message}]`
}

function assertAssistantMessage(
  message: AssistantMessage,
  turn: number,
  messages: readonly Message[],
): asserts message is AssistantMessage {
  if (!message || message.role !== 'assistant') {
    const error = new Error('model.next() must return an assistant message')
    Object.assign(error, { state: { turn, messages } })
    throw error
  }
}
