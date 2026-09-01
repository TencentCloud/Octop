import type { PermissionContext, PermissionResult } from './permissions.js'
import type { AgentEvent, Message, ToolInput } from './messages.js'

export type ToolInputField = {
  type?: 'string' | 'number' | 'boolean' | 'object' | 'array'
  items?: ToolInputField
  properties?: ToolInputSchema
  additionalProperties?: boolean
  minimum?: number
  maximum?: number
  required?: boolean
}

export type ToolInputSchema = Record<string, ToolInputField>

export type ToolExecutionContext = {
  messages: Message[]
  permissionContext: PermissionContext
  turn?: number
  emitEvent?: (event: AgentEvent) => void
}

export type ValidationResult =
  | { result: true }
  | { result: false; message: string; errorCode?: string }

export type Tool<Output = unknown> = {
  aliases: string[]
  description: string
  inputSchema: ToolInputSchema
  maxResultSizeChars: number
  name: string
  call(input: ToolInput, context: ToolExecutionContext): Promise<Output>
  checkPermissions(input: ToolInput, context: PermissionContext): Promise<PermissionResult>
  getPath?: (input: ToolInput) => string
  isConcurrencySafe(input: ToolInput): boolean
  isReadOnly(input: ToolInput): boolean
  validateInput(input: ToolInput, context: ToolExecutionContext): Promise<ValidationResult>
}

export type ToolDefinition<Input extends ToolInput, Output> = {
  aliases?: string[]
  description?: string
  inputSchema?: ToolInputSchema
  maxResultSizeChars?: number
  name: string
  call(input: Input, context: ToolExecutionContext): Promise<Output>
  checkPermissions?: (input: Input, context: PermissionContext) => Promise<PermissionResult>
  getPath?: (input: Input) => string
  isConcurrencySafe?: (input: Input) => boolean
  isReadOnly?: (input: Input) => boolean
  validateInput?: (input: Input, context: ToolExecutionContext) => Promise<ValidationResult>
}

/**
 * Minimal tool interface inspired by Claude Code's Tool.ts.
 *
 * A tool is not just a callable function. It owns input validation,
 * read-only metadata, optional path extraction, and tool-specific permission
 * checks. The agent loop can then enforce a consistent execution pipeline.
 */
export class ToolInputError extends Error {
  readonly issues: string[]
  readonly toolName: string

  constructor(toolName: string, issues: string[]) {
    super(`Invalid input for tool "${toolName}": ${issues.join('; ')}`)
    this.name = 'ToolInputError'
    this.toolName = toolName
    this.issues = issues
  }
}

export function buildTool<Input extends ToolInput = ToolInput, Output = unknown>(
  definition: ToolDefinition<Input, Output>,
): Tool<Output> {
  return {
    aliases: definition.aliases ?? [],
    description: definition.description ?? '',
    inputSchema: definition.inputSchema ?? {},
    maxResultSizeChars: definition.maxResultSizeChars ?? 100_000,
    name: definition.name,
    call: (input, context) => definition.call(input as Input, context),
    checkPermissions: definition.checkPermissions
      ? (input, context) => definition.checkPermissions?.(input as Input, context) as Promise<PermissionResult>
      : async input => ({ behavior: 'passthrough', updatedInput: input }),
    getPath: definition.getPath
      ? input => definition.getPath?.(input as Input) ?? ''
      : undefined,
    isConcurrencySafe: definition.isConcurrencySafe
      ? input => definition.isConcurrencySafe?.(input as Input) ?? false
      : () => false,
    isReadOnly: definition.isReadOnly
      ? input => definition.isReadOnly?.(input as Input) ?? false
      : () => false,
    validateInput: definition.validateInput
      ? (input, context) => definition.validateInput?.(input as Input, context) as Promise<ValidationResult>
      : async () => ({ result: true }),
  }
}

export function findToolByName(tools: readonly Tool[], name: string): Tool | undefined {
  return tools.find(tool => tool.name === name || tool.aliases.includes(name))
}

export function validateToolInput<Input extends ToolInput>(
  tool: Tool,
  input: unknown,
): Input {
  const schema = tool.inputSchema
  const issues: string[] = []

  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new ToolInputError(tool.name, ['input must be an object'])
  }

  const record = input as ToolInput
  for (const [field, rules] of Object.entries(schema)) {
    const value = record[field]
    if (rules.required && value === undefined) {
      issues.push(`${field} is required`)
      continue
    }
    if (value === undefined || !rules.type) continue
    if (rules.type === 'array' && !Array.isArray(value)) {
      issues.push(`${field} must be array`)
      continue
    }
    if (rules.type !== 'array' && typeof value !== rules.type) {
      issues.push(`${field} must be ${rules.type}`)
      continue
    }
    if (
      rules.type === 'array' &&
      rules.items &&
      (value as unknown[]).some(item => typeof item !== rules.items?.type)
    ) {
      issues.push(`${field} items must be ${rules.items.type}`)
    }
  }

  if (issues.length > 0) {
    throw new ToolInputError(tool.name, issues)
  }

  return record as Input
}
