import path from 'node:path'
import type { Tool } from './tool.js'
import type { ToolInput } from './messages.js'

export const PermissionBehavior = Object.freeze({
  ALLOW: 'allow',
  DENY: 'deny',
  ASK: 'ask',
  PASSTHROUGH: 'passthrough',
})

export type PermissionBehavior =
  (typeof PermissionBehavior)[keyof typeof PermissionBehavior]

export type PermissionMode = 'default' | 'acceptEdits' | 'plan'

export type PermissionDecisionReason = {
  type: 'policy' | 'tool' | 'path'
  reason: string
}

export type PermissionResult = {
  behavior: PermissionBehavior
  updatedInput?: ToolInput
  message?: string
  decisionReason?: PermissionDecisionReason
}

export type PermissionContext = {
  cwd: string
  mode: PermissionMode
  readableRoots: string[]
  writableRoots: string[]
  toolRules: Record<string, PermissionBehavior | undefined>
}

export function allow(updatedInput?: ToolInput): PermissionResult {
  return { behavior: PermissionBehavior.ALLOW, updatedInput }
}

export function deny(message: string, reason = message): PermissionResult {
  return {
    behavior: PermissionBehavior.DENY,
    message,
    decisionReason: { type: 'policy', reason },
  }
}

export function ask(message: string, reason = message): PermissionResult {
  return {
    behavior: PermissionBehavior.ASK,
    message,
    decisionReason: { type: 'policy', reason },
  }
}

export function passthrough(updatedInput?: ToolInput): PermissionResult {
  return { behavior: PermissionBehavior.PASSTHROUGH, updatedInput }
}

export function createPermissionContext({
  cwd = process.cwd(),
  mode = 'default',
  readableRoots = [cwd],
  writableRoots = [],
  toolRules = {},
}: Partial<PermissionContext> = {}): PermissionContext {
  return {
    cwd: path.resolve(cwd),
    mode,
    readableRoots: readableRoots.map(root => path.resolve(cwd, root)),
    writableRoots: writableRoots.map(root => path.resolve(cwd, root)),
    toolRules,
  }
}

export function isPathInside(candidatePath: string, rootPath: string): boolean {
  const candidate = path.resolve(candidatePath)
  const root = path.resolve(rootPath)
  const relative = path.relative(root, candidate)
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}

export function checkPathAccess(
  filePath: string,
  roots: readonly string[],
  operation: 'read' | 'write',
  input: ToolInput = {},
): PermissionResult {
  const absolutePath = path.resolve(filePath)
  const matchedRoot = roots.find(root => isPathInside(absolutePath, root))

  if (!matchedRoot) {
    return deny(
      `Permission denied: ${operation} outside allowed roots: ${absolutePath}`,
      `${operation} path is outside allowed roots`,
    )
  }

  return allow({ ...input, file_path: absolutePath })
}

export async function resolveToolPermission(
  tool: Tool,
  input: ToolInput,
  context: PermissionContext,
): Promise<PermissionResult> {
  const toolRule = context.toolRules[tool.name]
  if (toolRule === PermissionBehavior.DENY) {
    return deny(`Permission denied: tool "${tool.name}" is blocked`)
  }
  if (toolRule === PermissionBehavior.ALLOW) {
    return allow(input)
  }

  const toolSpecific = await tool.checkPermissions(input, context)
  if (
    toolSpecific.behavior &&
    toolSpecific.behavior !== PermissionBehavior.PASSTHROUGH
  ) {
    return toolSpecific
  }

  if (tool.isReadOnly(input)) {
    if (typeof tool.getPath === 'function') {
      return checkPathAccess(tool.getPath(input), context.readableRoots, 'read', input)
    }
    return allow(input)
  }

  if (typeof tool.getPath === 'function') {
    return checkPathAccess(tool.getPath(input), context.writableRoots, 'write', input)
  }

  if (context.mode === 'acceptEdits') {
    return allow(input)
  }

  return ask(`Tool "${tool.name}" requires permission`)
}
