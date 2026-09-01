import { createAssistantMessage, type AssistantMessage, type Message } from './agent-loop.js'
import type { ToolInput } from './messages.js'

export type ScriptedStep =
  | AssistantMessage
  | ((messages: readonly Message[]) => AssistantMessage | Promise<AssistantMessage>)

export function createToolCall(id: string, name: string, input: ToolInput = {}) {
  return { id, name, input }
}

export class ScriptedModel {
  private readonly steps: ScriptedStep[]
  private index = 0

  constructor(steps: readonly ScriptedStep[]) {
    this.steps = [...steps]
  }

  async next(messages: readonly Message[]): Promise<AssistantMessage> {
    if (this.index >= this.steps.length) {
      return createAssistantMessage('No scripted response left.')
    }

    const step = this.steps[this.index++]
    if (typeof step === 'function') {
      return step(messages)
    }

    return step
  }
}

export function assistantWithToolCalls(
  content: string,
  toolCalls: AssistantMessage['tool_calls'],
): AssistantMessage {
  return {
    role: 'assistant',
    content,
    tool_calls: toolCalls,
  }
}
