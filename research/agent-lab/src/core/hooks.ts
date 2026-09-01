import type { Message, ToolCall, ToolInput } from './messages.js'
import type { PermissionContext } from './permissions.js'
import type { Tool } from './tool.js'

export type ToolHookContext = {
  toolCall: ToolCall
  tool: Tool
  input: ToolInput
  messages: readonly Message[]
  permissionContext: PermissionContext
  turn: number
}

export type PreToolHookResult = {
  behavior?: 'allow' | 'deny'
  message?: string
  updatedInput?: ToolInput
  additionalContext?: string
}

export type PostToolHookResult = {
  output?: unknown
  additionalContext?: string
}

export type ErrorToolHookResult = {
  recoveredOutput?: unknown
  additionalContext?: string
}

export type NamedHook<Context, Result> = {
  name: string
  run(context: Context): Promise<Result | void>
}

export type ToolHooks = {
  pre?: readonly NamedHook<ToolHookContext, PreToolHookResult>[]
  post?: readonly NamedHook<ToolHookContext & { output: unknown }, PostToolHookResult>[]
  error?: readonly NamedHook<ToolHookContext & { error: Error }, ErrorToolHookResult>[]
}
