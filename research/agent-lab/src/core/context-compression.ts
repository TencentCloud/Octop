import type { ContextManager, ContextPreparation } from './context-manager.js'
import {
  createSystemMessage,
  createToolResultMessage,
  type Message,
  type ToolResultMessage,
} from './messages.js'

export type ConversationSummarizer = {
  summarize(messages: readonly Message[], maxChars: number): Promise<string>
}

export type CompactingContextOptions = {
  maxChars: number
  preserveRecentChars: number
  summaryMaxChars?: number
  toolReceiptMaxChars?: number
  delegate?: ContextManager
  summarizer?: ConversationSummarizer
}

export type WorkingState = {
  goal: string
  constraints: string[]
  decisions: string[]
  completed: string[]
  pending: string[]
  failedAttempts: Array<{ action: string; reason: string }>
  evidenceRefs: string[]
  notes: string[]
}

export type CanonicalizationResult = {
  messages: Message[]
  droppedOrphanToolResults: number
  synthesizedToolResults: number
}

type MessageUnit = {
  messages: Message[]
  chars: number
}

export class CompactingContextManager implements ContextManager {
  private readonly summaryMaxChars: number
  private readonly summarizer: ConversationSummarizer
  private readonly toolReceiptMaxChars: number

  constructor(private readonly options: CompactingContextOptions) {
    this.summaryMaxChars = options.summaryMaxChars ?? Math.max(1_000, Math.floor(options.maxChars * 0.25))
    this.summarizer = options.summarizer ?? StructuredConversationSummarizer
    this.toolReceiptMaxChars = options.toolReceiptMaxChars ?? 800
  }

  async prepare(messages: readonly Message[], turn: number): Promise<ContextPreparation> {
    const canonical = canonicalizeToolPairs(messages)
    const beforeChars = countChars(canonical.messages)
    const pre = await this.compactIfNeeded(canonical.messages)

    const delegated = this.options.delegate
      ? await this.options.delegate.prepare(pre.messages, turn)
      : { messages: pre.messages }
    const afterInjectionChars = countChars(delegated.messages)
    const postCanonical = canonicalizeToolPairs(delegated.messages)
    const post = await this.compactIfNeeded(postCanonical.messages)
    return {
      messages: post.messages,
      metadata: {
        ...delegated.metadata,
        droppedOrphanToolResults:
          canonical.droppedOrphanToolResults + postCanonical.droppedOrphanToolResults,
        synthesizedToolResults:
          canonical.synthesizedToolResults + postCanonical.synthesizedToolResults,
        compacted: pre.compacted || post.compacted,
        preCompacted: pre.compacted,
        postInjectionCompacted: post.compacted,
        summarizedMessages: pre.summarizedMessages + post.summarizedMessages,
        contextCharsBefore: beforeChars,
        contextCharsAfterInjection: afterInjectionChars,
        contextCharsAfter: countChars(post.messages),
        finalBudgetChars: this.options.maxChars,
      },
    }
  }

  private async compactIfNeeded(messages: readonly Message[]) {
    if (countChars(messages) <= this.options.maxChars) {
      return { messages: [...messages], compacted: false, summarizedMessages: 0 }
    }

    const latestUser = messages.findLast(message => message.role === 'user')
    const prefix: Message[] = []
    let prefixEnd = 0
    while (messages[prefixEnd]?.role === 'system') {
      prefix.push(messages[prefixEnd])
      prefixEnd++
    }

    const units = createMessageUnits(messages.slice(prefixEnd))
    const recent: MessageUnit[] = []
    const prefixChars = countChars(prefix)
    const available = Math.max(0, this.options.maxChars - prefixChars)
    const summaryReserve = Math.min(this.summaryMaxChars, Math.floor(available * 0.35))
    const recentTarget = Math.min(this.options.preserveRecentChars, Math.max(0, available - summaryReserve))
    let recentChars = 0
    while (units.length > 0 && (recentChars < recentTarget || recent.length === 0)) {
      const unit = units.pop()
      if (!unit) break
      recent.unshift(unit)
      recentChars += unit.chars
    }

    const oldMessages = units
      .flatMap(unit => unit.messages)
      .map(message => message.role === 'tool'
        ? createToolReceipt(message, this.toolReceiptMaxChars)
        : message)
    const summaryBudget = Math.max(
      0,
      Math.min(this.summaryMaxChars, this.options.maxChars - prefixChars - recentChars - 200),
    )
    const summary = summaryBudget >= 100
      ? await this.summarizer.summarize(oldMessages, summaryBudget)
      : ''
    let compacted = [
      ...prefix,
      ...(summary ? [createSystemMessage(`<conversation_summary>\n${summary}\n</conversation_summary>`)] : []),
      ...recent.flatMap(unit => unit.messages),
    ]
    if (latestUser && !compacted.some(message => message.role === 'user')) {
      const insertionIndex = prefix.length + (summary ? 1 : 0)
      compacted.splice(insertionIndex, 0, { ...latestUser })
    }
    compacted = enforceHardLimit(compacted, this.options.maxChars)
    return {
      messages: compacted,
      compacted: true,
      summarizedMessages: oldMessages.length,
    }
  }
}

export const StructuredConversationSummarizer: ConversationSummarizer = {
  async summarize(messages, maxChars) {
    return serializeWorkingState(buildWorkingState(messages), maxChars)
  },
}

/** Backward-compatible export for callers that supplied the old default explicitly. */
export const ExtractiveConversationSummarizer = StructuredConversationSummarizer

export function canonicalizeToolPairs(messages: readonly Message[]): CanonicalizationResult {
  const output: Message[] = []
  let droppedOrphanToolResults = 0
  let synthesizedToolResults = 0

  for (let index = 0; index < messages.length; index++) {
    const message = messages[index]!
    if (message.role === 'tool') {
      droppedOrphanToolResults++
      continue
    }

    output.push(cloneMessage(message))
    if (message.role !== 'assistant' || !message.tool_calls?.length) continue

    const expected = new Map(message.tool_calls.map(call => [call.id, call.name]))
    let cursor = index + 1
    while (cursor < messages.length && messages[cursor]?.role === 'tool') {
      const result = messages[cursor] as ToolResultMessage
      const toolName = expected.get(result.tool_call_id)
      if (toolName) {
        output.push({ ...result, tool_name: result.tool_name || toolName })
        expected.delete(result.tool_call_id)
      } else {
        droppedOrphanToolResults++
      }
      cursor++
    }
    index = cursor - 1

    for (const [toolCallId, toolName] of expected) {
      output.push(createToolResultMessage({
        toolCallId,
        toolName,
        isError: true,
        content: 'Tool execution result was unavailable; do not assume the tool succeeded.',
      }))
      synthesizedToolResults++
    }
  }

  return { messages: output, droppedOrphanToolResults, synthesizedToolResults }
}

export function buildWorkingState(messages: readonly Message[]): WorkingState {
  const users = messages.filter(message => message.role === 'user')
  const assistants = messages.filter(message => message.role === 'assistant')
  const toolResults = messages.filter((message): message is ToolResultMessage => message.role === 'tool')
  const firstRequest = users[0]?.content ?? ''
  const latestRequest = users.at(-1)?.content ?? firstRequest
  const constraints = users
    .flatMap(message => splitSentences(message.content))
    .filter(sentence => /\b(must|should|never|do not|don't|only|required?|constraint)\b/i.test(sentence))
  const decisions = assistants
    .flatMap(message => splitSentences(message.content))
    .filter(sentence => /\b(decid(?:e|ed)|choose|selected|will use|approach)\b/i.test(sentence))
  const completed = toolResults
    .filter(message => !message.is_error)
    .map(message => `${message.tool_name}#${message.tool_call_id}: ${singleLine(message.content)}`)
  const failedAttempts = toolResults
    .filter(message => message.is_error)
    .map(message => ({
      action: `${message.tool_name}#${message.tool_call_id}`,
      reason: singleLine(message.content),
    }))
  const evidenceRefs = [...new Set(messages.flatMap(message => [
    ...message.content.matchAll(/\b(?:memory|source|evidence)[-_ ]?id[=:"' ]+([a-zA-Z0-9_-]+)/gi),
    ...message.content.matchAll(/<memory\s+id="([^"]+)"/gi),
  ]).map(match => match[1]!).filter(Boolean))]
  const notes = messages
    .filter(message => message.role !== 'tool')
    .slice(-6)
    .map(message => `${message.role}: ${singleLine(message.content)}`)

  return {
    goal: singleLine(firstRequest),
    constraints: uniqueLimited(constraints, 8),
    decisions: uniqueLimited(decisions, 8),
    completed: uniqueLimited(completed, 12),
    pending: latestRequest ? [singleLine(latestRequest)] : [],
    failedAttempts: failedAttempts.slice(-8),
    evidenceRefs: evidenceRefs.slice(-20),
    notes: uniqueLimited(notes, 8),
  }
}

function serializeWorkingState(state: WorkingState, maxChars: number): string {
  const header = '<working_state schema_version="1.0">\n'
  const footer = '\n</working_state>'
  const body = JSON.stringify(state, null, 2)
  if (header.length + body.length + footer.length <= maxChars) return `${header}${body}${footer}`

  const compact: WorkingState = {
    ...state,
    constraints: [...state.constraints],
    decisions: [...state.decisions],
    completed: state.completed.slice(-4),
    pending: [...state.pending],
    failedAttempts: [...state.failedAttempts],
    evidenceRefs: [...state.evidenceRefs],
    notes: [],
  }
  const arrayFields: Array<keyof Pick<WorkingState,
    'completed' | 'failedAttempts' | 'decisions' | 'constraints' | 'evidenceRefs' | 'pending'
  >> = ['completed', 'failedAttempts', 'decisions', 'constraints', 'evidenceRefs', 'pending']
  let compactBody = JSON.stringify(compact)
  while (header.length + compactBody.length + footer.length > maxChars) {
    const field = arrayFields.find(candidate => compact[candidate].length > 0)
    if (!field) break
    compact[field].shift()
    compactBody = JSON.stringify(compact)
  }
  if (header.length + compactBody.length + footer.length <= maxChars) {
    return `${header}${compactBody}${footer}`
  }

  const emptyState: WorkingState = {
    goal: '',
    constraints: [],
    decisions: [],
    completed: [],
    pending: [],
    failedAttempts: [],
    evidenceRefs: [],
    notes: [],
  }
  const emptyBody = JSON.stringify(emptyState)
  if (header.length + emptyBody.length + footer.length <= maxChars) {
    return `${header}${emptyBody}${footer}`
  }

  const fallbackBody = '{}'
  return header.length + fallbackBody.length + footer.length <= maxChars
    ? `${header}${fallbackBody}${footer}`
    : ''
}

function createToolReceipt(message: ToolResultMessage, maxChars: number): ToolResultMessage {
  const normalized = singleLine(message.content)
  const content = normalized.length <= maxChars
    ? normalized
    : `${normalized.slice(0, maxChars)} [receipt truncated]`
  return {
    ...message,
    content: JSON.stringify({
      type: 'tool_receipt',
      tool: message.tool_name,
      tool_call_id: message.tool_call_id,
      success: !message.is_error,
      result: content,
    }),
  }
}

export function createMessageUnits(messages: readonly Message[]): MessageUnit[] {
  const units: MessageUnit[] = []
  for (let index = 0; index < messages.length; index++) {
    const message = messages[index]
    const grouped = [message]
    if (message.role === 'assistant' && message.tool_calls?.length) {
      const pending = new Set(message.tool_calls.map(call => call.id))
      while (index + 1 < messages.length) {
        const candidate = messages[index + 1]
        if (candidate.role !== 'tool' || !pending.has(candidate.tool_call_id)) break
        grouped.push(candidate)
        pending.delete(candidate.tool_call_id)
        index++
      }
    }
    units.push({ messages: grouped, chars: countChars(grouped) })
  }
  return units
}

function countChars(messages: readonly Message[]): number {
  return messages.reduce((total, message) => total + JSON.stringify(message).length, 0)
}

function cloneMessage(message: Message): Message {
  if (message.role !== 'assistant') return { ...message }
  return {
    ...message,
    tool_calls: message.tool_calls?.map(call => ({
      ...call,
      input: call.input ? { ...call.input } : undefined,
    })),
  }
}

function splitSentences(value: string): string[] {
  return value.split(/(?<=[.!?。！？])\s*|\n+/).map(singleLine).filter(Boolean)
}

function uniqueLimited(values: readonly string[], limit: number): string[] {
  return [...new Set(values.filter(Boolean))].slice(-limit)
}

function enforceHardLimit(messages: Message[], maxChars: number): Message[] {
  const bounded = messages.map(message => ({ ...message }))
  const marker = '\n[context truncated to final budget]'
  while (countChars(bounded) > maxChars) {
    const overflow = countChars(bounded) - maxChars
    const candidates = bounded
      .map((message, index) => ({ message, index }))
      .filter(({ message }) =>
        message.content.length > marker.length + 32 &&
        !message.content.startsWith('<conversation_summary>\n<working_state'),
      )
      .sort((a, b) => b.message.content.length - a.message.content.length)
    const candidate = candidates[0]
    if (!candidate) {
      const summaryIndex = bounded.findIndex(message =>
        message.content.startsWith('<conversation_summary>\n<working_state'),
      )
      if (summaryIndex < 0) break
      bounded.splice(summaryIndex, 1)
      continue
    }
    const keep = Math.max(32, candidate.message.content.length - overflow - marker.length - 8)
    candidate.message.content = `${candidate.message.content.slice(0, keep)}${marker}`
  }
  return bounded
}

function singleLine(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}
