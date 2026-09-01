import path from 'node:path'

import { createUserMessage } from '../src/core/messages.js'
import { ScriptedModel, assistantWithToolCalls, createToolCall } from '../src/core/mock-model.js'
import { createMemoryAgent } from '../src/memory/runtime.js'

const projectRoot = process.cwd()
const agent = await createMemoryAgent(path.join(projectRoot, 'memory-agent.config.json'))

const model = new ScriptedModel([
  assistantWithToolCalls('Saving a sourced experiment conclusion.', [
    createToolCall('memory_create_1', 'MemoryCreate', {
      kind: 'semantic',
      title: 'Retrieval is not reading',
      summary: 'Perfect recall can still produce a low answer score.',
      content: 'Temporal recall_all@50=1.0 while judge=0.40. The reader must reconstruct date chains, event anchors, relative time, and inclusive boundaries.',
      tags: ['reader', 'temporal', 'evaluation'],
      source: {
        type: 'observation',
        ref: 'full-eval-500',
        observed_at: new Date().toISOString(),
      },
      temporal: { event_time: '2026-07-11' },
      confidence: 0.95,
    }),
  ]),
  messages => {
    const memoryContext = messages.find(message => message.role === 'system')
    return {
      role: 'assistant',
      content: memoryContext
        ? `Recovered organized memory:\n${memoryContext.content}`
        : 'No relevant memory was injected.',
    }
  },
])

const result = await agent.run(model, [
  createUserMessage('Remember and explain our temporal reader experiment.'),
])

console.log(result.output)
