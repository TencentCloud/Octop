import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(__dirname, '..')

const port = Number(process.env.PORT ?? 4177)

const visibleFiles = [
  'README.md',
  'docs/longmemeval-data-flow.md',
  'src/core/messages.ts',
  'src/core/agent-loop.ts',
  'src/core/query-stream.ts',
  'src/core/context-manager.ts',
  'src/core/context-compression.ts',
  'src/core/model-stream.ts',
  'src/core/hooks.ts',
  'src/core/tool.ts',
  'src/core/tool-execution.ts',
  'src/core/tool-orchestration.ts',
  'src/core/permissions.ts',
  'src/core/mock-model.ts',
  'src/tools/read-file.ts',
  'src/tools/write-file.ts',
  'src/adapters/tokenhub-stream.ts',
  'src/adapters/openai-compatible-client.ts',
  'src/memory/types.ts',
  'src/memory/config.ts',
  'src/memory/store.ts',
  'src/memory/tools.ts',
  'src/memory/context-manager.ts',
  'src/memory/evidence-report.ts',
  'src/memory/evidence-reader-subagent.ts',
  'src/memory/runtime.ts',
  'memory-agent.config.json',
  'test/agent-loop.test.ts',
  'test/memory-agent.test.ts',
  'test/evidence-report.test.ts',
  'test/runtime-extensions.test.ts',
  'examples/basic-loop.ts',
  'examples/memory-agent.ts',
  'eval/longmemeval-smoke.ts',
]

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  })
  response.end(JSON.stringify(payload, null, 2))
}

async function readVisibleFiles() {
  const files = []
  for (const relativePath of visibleFiles) {
    const absolutePath = path.join(projectRoot, relativePath)
    try {
      files.push({
        path: relativePath,
        content: await readFile(absolutePath, 'utf8'),
      })
    } catch (error) {
      files.push({
        path: relativePath,
        content: `Unable to read file: ${error.message}`,
      })
    }
  }
  return files
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? '/', `http://${request.headers.host}`)

  if (url.pathname === '/api/files') {
    sendJson(response, 200, {
      updatedAt: new Date().toISOString(),
      files: await readVisibleFiles(),
    })
    return
  }

  if (url.pathname === '/' || url.pathname === '/index.html') {
    response.writeHead(200, {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store',
    })
    response.end(await readFile(path.join(__dirname, 'index.html'), 'utf8'))
    return
  }

  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
  response.end('Not found')
})

server.listen(port, '127.0.0.1', () => {
  console.log(`Agent Lab code viewer: http://127.0.0.1:${port}`)
})
