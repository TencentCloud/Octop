import type { PermissionContext } from './permissions.js'
import type { Tool } from './tool.js'
import type { AgentEvent, AssistantMessage, Message } from './messages.js'
import type { ContextManager } from './context-manager.js'
import { runQueryStream } from './query-stream.js'
import type { AgentModelLike } from './model-stream.js'
import type { ToolHooks } from './hooks.js'

export type {
  AgentEvent,
  AssistantMessage,
  Message,
  ToolCall,
  ToolInput,
  ToolResultMessage,
  UserMessage,
  SystemMessage,
} from './messages.js'
export {
  createAssistantMessage,
  createSystemMessage,
  createToolResultMessage,
  createUserMessage,
} from './messages.js'

export type ModelContext = {
  tools: readonly Tool[]
  permissionContext: PermissionContext
  turn: number
  toolChoice?: 'auto' | 'required' | 'none'
}

export type AgentModel = {
  next(messages: readonly Message[], context: ModelContext): Promise<AssistantMessage>
}

export type RunAgentLoopParams = {
  model: AgentModelLike
  tools: readonly Tool[]
  permissionContext: PermissionContext
  messages: readonly Message[]
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
  onEvent?: (event: AgentEvent) => void
  contextManager?: ContextManager
  hooks?: ToolHooks
}

export type RunAgentLoopResult = {
  status: 'completed' | 'max_turns_exceeded'
  messages: Message[]
  output: string | null
  events: AgentEvent[]
}

export class AgentLoopError extends Error {
  readonly state: unknown

  constructor(message: string, state: unknown) {
    super(message)
    this.name = 'AgentLoopError'
    this.state = state
  }
}

export async function runAgentLoop({
  model,
  tools,
  permissionContext,
  messages,
  maxTurns = 10,
  maxToolCallsPerTurn,
  reserveFinalAnswerTurn,
  answerAfterToolNames,
  toolCallLimits,
  toolPrerequisites,
  requireAnyToolBeforeAnswer,
  requireToolBeforeAnswerAfter,
  onEvent,
  contextManager,
  hooks,
}: RunAgentLoopParams): Promise<RunAgentLoopResult> {
  const events: AgentEvent[] = []
  const stream = runQueryStream({
    model,
    tools,
    permissionContext,
    messages,
    maxTurns,
    maxToolCallsPerTurn,
    reserveFinalAnswerTurn,
    answerAfterToolNames,
    toolCallLimits,
    toolPrerequisites,
    requireAnyToolBeforeAnswer,
    requireToolBeforeAnswerAfter,
    contextManager,
    hooks,
  })

  while (true) {
    const next = await stream.next()
    if (next.done) {
      return { ...next.value, events }
    }
    const event = next.value
    events.push(event)
    onEvent?.(event)
  }
}
