import path from 'node:path'
import { createPermissionContext } from '../src/core/permissions.js'
import { createUserMessage, runAgentLoop } from '../src/core/agent-loop.js'
import {
  ScriptedModel,
  assistantWithToolCalls,
  createToolCall,
} from '../src/core/mock-model.js'
import { ReadFileTool } from '../src/tools/read-file.js'
import { WriteFileTool } from '../src/tools/write-file.js'

const cwd = process.cwd()
const scratchPath = path.join(cwd, 'tmp', 'demo-note.txt')

const model = new ScriptedModel([
  assistantWithToolCalls('I will write a note first.', [
    createToolCall('call_1', 'WriteFile', {
      file_path: scratchPath,
      content: 'agent loop is alive\n',
    }),
  ]),
  assistantWithToolCalls('Now I will read the note back.', [
    createToolCall('call_2', 'ReadFile', {
      file_path: scratchPath,
    }),
  ]),
  messages => {
    const lastToolResult = messages.findLast(message => message.role === 'tool')
    return {
      role: 'assistant',
      content: `Done. Last tool result: ${lastToolResult?.content}`,
    }
  },
])

const result = await runAgentLoop({
  model,
  tools: [ReadFileTool, WriteFileTool],
  permissionContext: createPermissionContext({
    cwd,
    readableRoots: [cwd],
    writableRoots: [path.join(cwd, 'tmp')],
  }),
  messages: [createUserMessage('Create and read a note.')],
  onEvent: event => {
    if (event.type.startsWith('tool_')) {
      console.log(event)
    }
  },
})

console.log(result.output)
