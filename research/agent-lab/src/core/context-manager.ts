import type { Message } from './messages.js'

export type ContextPreparation = {
  messages: Message[]
  metadata?: Record<string, unknown>
}

export type ContextManager = {
  prepare(messages: readonly Message[], turn: number): Promise<ContextPreparation>
}

export const PassthroughContextManager: ContextManager = {
  async prepare(messages) {
    return { messages: [...messages] }
  },
}
