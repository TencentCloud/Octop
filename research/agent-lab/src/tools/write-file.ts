import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { buildTool } from '../core/tool.js'

type WriteFileInput = {
  file_path: string
  content: string
}

type WriteFileOutput = {
  file_path: string
  bytes: number
}

export const WriteFileTool = buildTool<WriteFileInput, WriteFileOutput>({
  name: 'WriteFile',
  description: 'Write a UTF-8 text file inside an allowed writable root.',
  inputSchema: {
    file_path: { type: 'string', required: true },
    content: { type: 'string', required: true },
  },
  isReadOnly: () => false,
  getPath: input => input.file_path,
  async call(input) {
    await mkdir(path.dirname(input.file_path), { recursive: true })
    await writeFile(input.file_path, input.content, 'utf8')
    return {
      file_path: input.file_path,
      bytes: Buffer.byteLength(input.content, 'utf8'),
    }
  },
})
