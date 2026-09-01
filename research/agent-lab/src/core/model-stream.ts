import type { AgentModel, ModelContext } from './agent-loop.js'
import type { AssistantMessage, Message, ToolCall, ToolInput } from './messages.js'

export type ModelStreamEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'reasoning_delta'; text: string }
  | { type: 'tool_call_start'; id: string; name: string }
  | { type: 'tool_input_delta'; id: string; partialJson: string }
  | { type: 'tool_call'; call: ToolCall }
  | { type: 'end' }

export type StreamingAgentModel = {
  stream(messages: readonly Message[], context: ModelContext): AsyncIterable<ModelStreamEvent>
}

export type AgentModelLike = AgentModel | StreamingAgentModel

export function isStreamingAgentModel(model: AgentModelLike): model is StreamingAgentModel {
  return 'stream' in model && typeof model.stream === 'function'
}

type PendingToolCall = {
  id: string
  name: string
  partialJson: string
  directInput?: ToolInput
}

export class InvalidStreamedToolInputError extends Error {
  readonly toolCallId: string
  readonly toolName: string

  constructor(call: PendingToolCall, cause: unknown) {
    const message = cause instanceof Error ? cause.message : String(cause)
    super(`Invalid streamed input for ${call.name} (${call.id}): ${message}`)
    this.name = 'InvalidStreamedToolInputError'
    this.toolCallId = call.id
    this.toolName = call.name
  }
}

/** Collects provider deltas without ever mixing private reasoning into answer text. */
export class AssistantStreamAssembler {
  private text = ''
  private readonly calls = new Map<string, PendingToolCall>()

  consume(event: ModelStreamEvent): void {
    switch (event.type) {
      case 'text_delta':
        this.text += event.text
        break
      case 'reasoning_delta':
      case 'end':
        break
      case 'tool_call_start':
        this.calls.set(event.id, { id: event.id, name: event.name, partialJson: '' })
        break
      case 'tool_input_delta': {
        const call = this.calls.get(event.id)
        if (!call) throw new Error(`Tool input delta arrived before tool start: ${event.id}`)
        call.partialJson += event.partialJson
        break
      }
      case 'tool_call':
        this.calls.set(event.call.id, {
          id: event.call.id,
          name: event.call.name,
          partialJson: '',
          directInput: event.call.input ?? {},
        })
        break
    }
  }

  finish(): AssistantMessage {
    const toolCalls = [...this.calls.values()].map(call => ({
      id: call.id,
      name: call.name,
      input: call.directInput ?? parseToolInput(call),
    }))
    return {
      role: 'assistant',
      content: this.text,
      ...(toolCalls.length > 0 ? { tool_calls: toolCalls } : {}),
    }
  }
}

function parseToolInput(call: PendingToolCall): ToolInput {
  if (!call.partialJson.trim()) return {}
  try {
    const parsed = JSON.parse(call.partialJson) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('input must be a JSON object')
    }
    return parsed as ToolInput
  } catch (error) {
    throw new InvalidStreamedToolInputError(call, error)
  }
}
