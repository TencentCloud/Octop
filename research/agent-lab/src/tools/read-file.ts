import { readFile } from 'node:fs/promises'
import { buildTool } from '../core/tool.js'

type ReadFileInput = {
  file_path: string
}

type ReadFileOutput = {
  file_path: string
  content: string
}

export const ReadFileTool = buildTool<ReadFileInput, ReadFileOutput>({
  name: 'ReadFile',
  description: 'Read a UTF-8 text file from an allowed root.',
  inputSchema: {
    file_path: { type: 'string', required: true },
  },
  isReadOnly: () => true,
  isConcurrencySafe: () => true,
  getPath: input => input.file_path,
  async call(input) {
    const content = await readFile(input.file_path, 'utf8')
    return {
      file_path: input.file_path,
      content,
    }
  },
})
