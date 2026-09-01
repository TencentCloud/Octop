export type ToolInput = Record<string, unknown>

export type ToolCall = {
  id: string
  name: string
  input?: ToolInput
}

export type UserMessage = {
  role: 'user'
  content: string
}

export type SystemMessage = {
  role: 'system'
  content: string
}

export type AssistantMessage = {
  role: 'assistant'
  content: string
  tool_calls?: ToolCall[]
}

export type ToolResultMessage = {
  role: 'tool'
  tool_call_id: string
  tool_name: string
  is_error: boolean
  content: string
}

export type Message = SystemMessage | UserMessage | AssistantMessage | ToolResultMessage

export type AgentEvent =
  | { type: 'model_turn_start'; turn: number }
  | { type: 'model_stream_start'; turn: number }
  | { type: 'assistant_text_delta'; turn: number; text: string }
  | { type: 'assistant_reasoning_delta'; turn: number; text: string }
  | { type: 'tool_input_delta'; turn: number; toolCallId: string; partialJson: string }
  | { type: 'model_stream_end'; turn: number }
  | { type: 'model_empty_response_retry'; turn: number; reason: 'reasoning_only' | 'empty' }
  | { type: 'model_tool_input_retry'; turn: number; toolName: string; error: string }
  | { type: 'model_premature_answer_retry'; turn: number; requiredTools: string[] }
  | { type: 'context_prepared'; turn: number; metadata: Record<string, unknown> }
  | { type: 'subagent_start'; turn: number; subagentId: string; kind: string; objective: string }
  | {
      type: 'subagent_end'
      turn: number
      subagentId: string
      kind: string
      status: string
      childTurns: number
      childToolCalls: string[]
    }
  | { type: 'subagent_error'; turn: number; subagentId: string; kind: string; error: string }
  | {
      type: 'answer_guard_applied'
      turn: number
      decisionKind: string
      expected: number | string
      observed: number | string | null
    }
  | { type: 'hook_start'; turn: number; hook: string; phase: 'pre' | 'post' | 'error'; toolName: string }
  | { type: 'hook_end'; turn: number; hook: string; phase: 'pre' | 'post' | 'error'; toolName: string }
  | { type: 'assistant_message'; turn: number; message: AssistantMessage }
  | { type: 'done'; turn: number; message: AssistantMessage }
  | { type: 'tool_error'; turn: number; toolName: string; error: string }
  | {
      type: 'tool_permission_denied'
      turn: number
      toolName: string
      behavior: string
      reason: unknown
    }
  | { type: 'tool_call_start'; turn: number; toolName: string; input: ToolInput }
  | { type: 'tool_call_end'; turn: number; toolName: string; output: unknown }

export function createUserMessage(content: string): UserMessage {
  return { role: 'user', content }
}

export function createSystemMessage(content: string): SystemMessage {
  return { role: 'system', content }
}

export function createAssistantMessage(content: string): AssistantMessage {
  return { role: 'assistant', content }
}

export function createToolResultMessage({
  toolCallId,
  toolName,
  content,
  isError = false,
}: {
  toolCallId: string
  toolName: string
  content: string
  isError?: boolean
}): ToolResultMessage {
  return {
    role: 'tool',
    tool_call_id: toolCallId,
    tool_name: toolName,
    is_error: isError,
    content,
  }
}
