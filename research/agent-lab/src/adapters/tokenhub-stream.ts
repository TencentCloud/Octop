import type { ModelContext } from '../core/agent-loop.js'
import type { Message } from '../core/messages.js'
import type { ModelStreamEvent, StreamingAgentModel } from '../core/model-stream.js'

export type TokenHubChunk = {
  choices?: Array<{
    delta?: {
      content?: string | null
      reasoning_content?: string | null
      tool_calls?: Array<{
        index: number
        id?: string
        function?: {
          name?: string
          arguments?: string
        }
      }>
    }
    finish_reason?: string | null
  }>
}

export type TokenHubStreamRequest = (
  messages: readonly Message[],
  context: ModelContext,
) => AsyncIterable<TokenHubChunk>

/** Provider boundary for OpenAI-compatible TokenHub streaming chunks. */
export function createTokenHubStreamingModel(request: TokenHubStreamRequest): StreamingAgentModel {
  return {
    async *stream(messages, context) {
      yield* adaptTokenHubChunks(request(messages, context))
    },
  }
}

export async function* adaptTokenHubChunks(
  chunks: AsyncIterable<TokenHubChunk>,
): AsyncGenerator<ModelStreamEvent> {
  const calls = new Map<number, { id: string; name: string; started: boolean }>()

  for await (const chunk of chunks) {
    for (const choice of chunk.choices ?? []) {
      const delta = choice.delta
      if (!delta) continue
      if (delta.reasoning_content) {
        yield { type: 'reasoning_delta', text: delta.reasoning_content }
      }
      if (delta.content) {
        yield { type: 'text_delta', text: delta.content }
      }
      for (const toolDelta of delta.tool_calls ?? []) {
        const current = calls.get(toolDelta.index) ?? {
          id: toolDelta.id ?? `tool_${toolDelta.index}`,
          name: '',
          started: false,
        }
        if (toolDelta.id) current.id = toolDelta.id
        if (toolDelta.function?.name) current.name += toolDelta.function.name

        const argumentDelta = toolDelta.function?.arguments
        if (argumentDelta !== undefined && !current.started) {
          if (!current.name) throw new Error(`TokenHub tool call ${current.id} emitted arguments before its name`)
          yield { type: 'tool_call_start', id: current.id, name: current.name }
          current.started = true
        }
        if (argumentDelta) {
          yield { type: 'tool_input_delta', id: current.id, partialJson: argumentDelta }
        }
        calls.set(toolDelta.index, current)
      }
    }
  }

  for (const call of calls.values()) {
    if (!call.started) {
      if (!call.name) throw new Error(`TokenHub tool call ${call.id} has no function name`)
      yield { type: 'tool_call_start', id: call.id, name: call.name }
    }
  }
  yield { type: 'end' }
}
