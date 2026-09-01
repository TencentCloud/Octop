import { randomUUID } from 'node:crypto'

import { runAgentLoop, type RunAgentLoopResult } from './agent-loop.js'
import {
  InMemoryChildSidechainStore,
  type ChildSidechainRecord,
  type ChildSidechainStore,
} from './child-sidechain.js'
import { PassthroughContextManager, type ContextManager } from './context-manager.js'
import { createSystemMessage, createUserMessage, type AgentEvent, type Message } from './messages.js'
import type { AgentModelLike } from './model-stream.js'
import type { PermissionContext } from './permissions.js'
import {
  InMemoryResultLedgerStore,
  summarizeLedgerResult,
  type ResultLedgerStore,
} from './result-ledger.js'
import { buildTool, findToolByName, type Tool } from './tool.js'
import {
  parseEvidenceResult,
  reconcileObservedEvidenceCoverage,
  type EvidenceCoverageObservation,
} from '../memory/evidence-result.js'

const FORK_SUBAGENT_TOOL_NAME = 'ForkSubagent'

export type RunForkSubagentParams = {
  model: AgentModelLike
  tools: readonly Tool[]
  permissionContext: PermissionContext
  prompt: string
  messages?: readonly Message[]
  description: string
  objective?: string
  kind?: string
  systemPrompt?: string
  contextRefs?: readonly string[]
  contextPrelude?: string
  contextManager?: ContextManager
  maxTurns?: number
  maxToolCallsPerTurn?: number
  toolCallLimits?: Readonly<Record<string, number>>
  reserveFinalAnswerTurn?: boolean
  sidechainStore?: ChildSidechainStore
  subagentId?: string
  parentTurn?: number
  emitEvent?: (event: AgentEvent) => void
}

export type RunForkSubagentResult = {
  subagentId: string
  result: RunAgentLoopResult
}

export async function runForkSubagent({
  model,
  tools,
  permissionContext,
  prompt,
  messages,
  description,
  objective = prompt,
  kind = 'general',
  systemPrompt = defaultSubagentSystemPrompt(),
  contextRefs = [],
  contextPrelude = '',
  contextManager = PassthroughContextManager,
  maxTurns = 6,
  maxToolCallsPerTurn = 2,
  toolCallLimits,
  reserveFinalAnswerTurn = true,
  sidechainStore = new InMemoryChildSidechainStore(),
  subagentId = randomUUID(),
  parentTurn = 0,
  emitEvent,
}: RunForkSubagentParams): Promise<RunForkSubagentResult> {
  const startedAtMs = Date.now()
  const startedAt = new Date(startedAtMs).toISOString()
  const childTools = tools.filter(tool => tool.name !== FORK_SUBAGENT_TOOL_NAME)
  const initialMessages: Message[] = messages
    ? [...messages]
    : [
        createSystemMessage(systemPrompt),
        createUserMessage(buildDelegationMessage(prompt, objective, contextRefs, contextPrelude)),
      ]
  const runningRecord: ChildSidechainRecord = {
    id: subagentId,
    kind,
    description,
    objective,
    status: 'running',
    allowedTools: childTools.map(tool => tool.name),
    messages: initialMessages,
    events: [],
    output: null,
    startedAt,
  }

  await sidechainStore.put(runningRecord)
  emitEvent?.({ type: 'subagent_start', turn: parentTurn, subagentId, kind, objective })

  try {
    const result = await runAgentLoop({
      model,
      tools: childTools,
      permissionContext,
      messages: initialMessages,
      contextManager,
      maxTurns,
      maxToolCallsPerTurn,
      toolCallLimits,
      reserveFinalAnswerTurn,
    })
    const childToolCalls = result.events.flatMap(event =>
      event.type === 'tool_call_start' ? [event.toolName] : [],
    )
    await sidechainStore.put({
      ...runningRecord,
      status: result.status,
      messages: result.messages,
      events: result.events,
      output: result.output,
      completedAt: new Date().toISOString(),
      durationMs: Date.now() - startedAtMs,
    })
    emitEvent?.({
      type: 'subagent_end',
      turn: parentTurn,
      subagentId,
      kind,
      status: result.status,
      childTurns: result.events.filter(event => event.type === 'model_turn_start').length,
      childToolCalls,
    })
    return { subagentId, result }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await sidechainStore.put({
      ...runningRecord,
      status: 'failed',
      error: message,
      completedAt: new Date().toISOString(),
      durationMs: Date.now() - startedAtMs,
    })
    emitEvent?.({ type: 'subagent_error', turn: parentTurn, subagentId, kind, error: message })
    throw error
  }
}

type ForkSubagentInput = {
  description: string
  prompt: string
  allowed_tools: string[]
  max_turns?: number
  context_refs?: string[]
}

export function createForkSubagentTool({
  model,
  availableTools,
  sidechainStore = new InMemoryChildSidechainStore(),
  resultLedger = new InMemoryResultLedgerStore(),
  resultMode = 'inline',
  defaultMaxTurns = 6,
  systemPrompt,
  contextManager,
  structuredEvidence = false,
  evidenceCompatibility = 'current',
  resolveContextPrelude,
}: {
  model: AgentModelLike
  availableTools: readonly Tool[]
  sidechainStore?: ChildSidechainStore
  resultLedger?: ResultLedgerStore
  resultMode?: 'inline' | 'ledger'
  defaultMaxTurns?: number
  systemPrompt?: string
  contextManager?: ContextManager
  structuredEvidence?: boolean
  evidenceCompatibility?: 'current' | 'v51'
  resolveContextPrelude?: (contextRefs: readonly string[], prompt: string) => Promise<string>
}): Tool {
  return buildTool<ForkSubagentInput, unknown>({
    name: FORK_SUBAGENT_TOOL_NAME,
    description: 'Delegate one bounded task to an isolated subagent with an explicit tool allowlist. The child returns a compact result while its transcript stays in a separate sidechain.',
    inputSchema: {
      description: { type: 'string', required: true },
      prompt: { type: 'string', required: true },
      allowed_tools: { type: 'array', items: { type: 'string' }, required: true },
      max_turns: { type: 'number', minimum: 1, maximum: defaultMaxTurns },
      context_refs: { type: 'array', items: { type: 'string' } },
    },
    maxResultSizeChars: 20_000,
    // The wrapper mutates no state itself. Every child tool call still passes
    // through the child's normal permission checks.
    isReadOnly: () => true,
    isConcurrencySafe: input => resolveAllowedTools(input.allowed_tools, availableTools)
      .every(tool => tool.isReadOnly({}) && tool.isConcurrencySafe({})),
    validateInput: async input => {
      if (!input.description.trim()) return { result: false, message: 'description must not be empty' }
      if (!input.prompt.trim()) return { result: false, message: 'prompt must not be empty' }
      if (input.allowed_tools.length === 0) return { result: false, message: 'allowed_tools must not be empty' }
      if (input.allowed_tools.includes(FORK_SUBAGENT_TOOL_NAME)) {
        return { result: false, message: 'ForkSubagent cannot delegate ForkSubagent recursively' }
      }
      const unknown = input.allowed_tools.filter(name => !findToolByName(availableTools, name))
      if (unknown.length > 0) return { result: false, message: `unknown allowed tools: ${unknown.join(', ')}` }
      if (input.max_turns !== undefined && (!Number.isInteger(input.max_turns) || input.max_turns < 1 || input.max_turns > defaultMaxTurns)) {
        return { result: false, message: `max_turns must be an integer between 1 and ${defaultMaxTurns}` }
      }
      return { result: true }
    },
    async call(input, executionContext) {
      const tools = resolveAllowedTools(input.allowed_tools, availableTools)
      const contextPrelude = resolveContextPrelude
        ? await resolveContextPrelude(input.context_refs ?? [], input.prompt)
        : ''
      const { subagentId, result } = await runForkSubagent({
        model,
        tools,
        permissionContext: executionContext.permissionContext,
        prompt: input.prompt,
        description: input.description,
        contextRefs: input.context_refs,
        contextPrelude,
        maxTurns: input.max_turns ?? defaultMaxTurns,
        systemPrompt,
        contextManager,
        toolCallLimits: { MemorySearch: 6, MemoryEvidenceBundle: 4 },
        sidechainStore,
        parentTurn: executionContext.turn,
        emitEvent: executionContext.emitEvent,
      })
      const output = result.output ?? ''
      if (resultMode === 'ledger') {
        const resultId = randomUUID()
        const summary = summarizeLedgerResult(output)
        const parsedEvidence = structuredEvidence
          ? evidenceCompatibility === 'v51'
            ? parseEvidenceResult(output)
            : reconcileObservedEvidenceCoverage(
              parseEvidenceResult(output),
              observeEvidenceCoverage(result.messages, contextPrelude, result.status),
            )
          : null
        const discoveredEvidence = extractPreservedToolEvidence(result.messages, input.prompt)
        await resultLedger.put({
          id: resultId,
          subagentId,
          kind: 'general',
          description: input.description,
          objective: input.prompt,
          status: result.status,
          summary,
          output,
          ...(contextPrelude ? { contextPrelude } : {}),
          ...(discoveredEvidence ? { discoveredEvidence } : {}),
          ...(parsedEvidence?.result ? { evidenceResult: parsedEvidence.result } : {}),
          ...(parsedEvidence && !parsedEvidence.valid ? { evidenceResultErrors: parsedEvidence.errors } : {}),
          ...(parsedEvidence && evidenceCompatibility !== 'v51' ? {
            evidenceFactValid: parsedEvidence.factValid,
            evidenceCoverageComplete: parsedEvidence.coverageComplete,
          } : {}),
          ...(evidenceCompatibility !== 'v51' && parsedEvidence?.factErrors.length
            ? { evidenceFactErrors: parsedEvidence.factErrors }
            : {}),
          ...(evidenceCompatibility !== 'v51' && parsedEvidence?.coverageErrors.length
            ? { evidenceCoverageErrors: parsedEvidence.coverageErrors }
            : {}),
        })
        return {
          result_id: resultId,
          subagent_id: subagentId,
          status: result.status,
          summary,
          evidence_result_valid: parsedEvidence?.valid ?? null,
          ...(evidenceCompatibility === 'v51' ? {} : {
            fact_packet_valid: parsedEvidence?.factValid ?? null,
            coverage_complete: parsedEvidence?.coverageComplete ?? null,
          }),
          coverage_status: parsedEvidence?.result?.coverage_status ?? null,
          coverage_stop_reason: parsedEvidence?.result?.coverage?.stop_reason ?? null,
          unexplored_source_count: parsedEvidence?.result?.unexplored_source_refs.length ?? null,
          output_available_to: 'CompileEvidence',
          turns: result.events.filter(event => event.type === 'model_turn_start').length,
          tool_calls: result.events.flatMap(event =>
            event.type === 'tool_call_start' ? [event.toolName] : [],
          ),
        }
      }
      return {
        subagent_id: subagentId,
        status: result.status,
        output: result.output,
        turns: result.events.filter(event => event.type === 'model_turn_start').length,
        tool_calls: result.events.flatMap(event =>
          event.type === 'tool_call_start' ? [event.toolName] : [],
        ),
      }
    },
  })
}

export function observeEvidenceCoverage(
  messages: readonly Message[],
  contextPrelude = '',
  status: RunAgentLoopResult['status'] = 'completed',
): EvidenceCoverageObservation {
  const assigned = new Set(extractJsonStringFields(contextPrelude, 'source_ref'))
  const inspected = new Set(assigned)
  const discovered = new Set<string>()
  const lastReadWindow = new Map<string, { sourceRef: string; hasMore: boolean }>()
  let searchCalls = 0
  let trailingSearchesWithoutNewSources = 0
  let bundleTruncated = false

  for (const message of messages) {
    if (message.role !== 'tool' || message.is_error) continue
    if (message.tool_name === 'MemorySearch') {
      searchCalls++
      const before = discovered.size
      try {
        const hits = JSON.parse(message.content) as unknown
        if (Array.isArray(hits)) {
          for (const item of hits) {
            if (!item || typeof item !== 'object' || Array.isArray(item)) continue
            const hit = item as Record<string, unknown>
            if (typeof hit.source_ref !== 'string') continue
            discovered.add(hit.source_ref)
            if (hit.summary_complete === true) inspected.add(hit.source_ref)
          }
        }
      } catch { /* malformed tool output remains unobserved */ }
      trailingSearchesWithoutNewSources = discovered.size === before
        ? trailingSearchesWithoutNewSources + 1
        : 0
      continue
    }
    if (message.tool_name === 'MemoryRead') {
      try {
        const record = JSON.parse(message.content) as Record<string, unknown>
        const source = isRecord(record.source) ? record.source : {}
        const window = isRecord(record.read_window) ? record.read_window : {}
        if (typeof source.ref === 'string') {
          inspected.add(source.ref)
          if (typeof record.id === 'string') {
            lastReadWindow.set(record.id, { sourceRef: source.ref, hasMore: window.has_more === true })
          }
        }
      } catch { /* malformed tool output remains unobserved */ }
      continue
    }
    if (message.tool_name === 'MemoryEvidenceBundle') {
      try {
        const bundle = JSON.parse(message.content) as Record<string, unknown>
        const clusters = Array.isArray(bundle.source_clusters) ? bundle.source_clusters : []
        for (const item of clusters) {
          if (!isRecord(item) || typeof item.source_ref !== 'string') continue
          discovered.add(item.source_ref)
          inspected.add(item.source_ref)
        }
        const stats = isRecord(bundle.stats) ? bundle.stats : {}
        if (stats.truncated === true) bundleTruncated = true
      } catch { /* malformed tool output remains unobserved */ }
    }
  }

  return {
    assigned_source_refs: [...assigned],
    inspected_source_refs: [...inspected],
    unread_source_refs: [...new Set([...lastReadWindow.values()]
      .filter(window => window.hasMore)
      .map(window => window.sourceRef))],
    search_calls: searchCalls,
    trailing_searches_without_new_sources: trailingSearchesWithoutNewSources,
    bundle_truncated: bundleTruncated,
    max_turns_exceeded: status === 'max_turns_exceeded',
  }
}

function extractJsonStringFields(value: string, field: string): string[] {
  const pattern = new RegExp(`"${field}"\\s*:\\s*("(?:\\\\.|[^"\\\\])*")`, 'g')
  const values: string[] = []
  for (const match of value.matchAll(pattern)) {
    try {
      const parsed = JSON.parse(match[1] ?? '') as unknown
      if (typeof parsed === 'string' && parsed.trim()) values.push(parsed.trim())
    } catch { /* ignore malformed embedded JSON */ }
  }
  return [...new Set(values)]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function extractPreservedToolEvidence(messages: readonly Message[], task = ''): string {
  const taskTokens = contentTokens(task)
  const searchHits = messages.flatMap(message => {
    if (message.role !== 'tool' || message.tool_name !== 'MemorySearch' || message.is_error) return []
    try {
      const parsed = JSON.parse(message.content) as unknown
      if (!Array.isArray(parsed)) return []
      return parsed.flatMap(item => {
        if (!item || typeof item !== 'object' || Array.isArray(item)) return []
        const hit = item as Record<string, unknown>
        if (hit.kind !== 'event' || hit.summary_complete !== true || typeof hit.summary !== 'string') return []
        return [{
          evidence_key: typeof hit.id === 'string' ? hit.id : undefined,
          memory_id: typeof hit.id === 'string' ? hit.id : undefined,
          source_ref: typeof hit.source_ref === 'string' ? hit.source_ref : undefined,
          source_refs: Array.isArray(hit.source_refs) ? hit.source_refs.filter(ref => typeof ref === 'string') : [],
          source_date: typeof hit.event_time === 'string' ? hit.event_time : undefined,
          speaker: hit.speaker === 'user' || hit.speaker === 'assistant' ? hit.speaker : undefined,
          excerpt: hit.summary,
        }]
      })
    } catch {
      return []
    }
  })
  const readHits = messages.flatMap(message => {
    if (message.role !== 'tool' || message.tool_name !== 'MemoryRead' || message.is_error) return []
    try {
      const record = JSON.parse(message.content) as Record<string, unknown>
      if (typeof record.id !== 'string' || typeof record.content !== 'string') return []
      const source = record.source && typeof record.source === 'object' && !Array.isArray(record.source)
        ? record.source as Record<string, unknown>
        : {}
      const temporal = record.temporal && typeof record.temporal === 'object' && !Array.isArray(record.temporal)
        ? record.temporal as Record<string, unknown>
        : {}
      const window = record.read_window && typeof record.read_window === 'object' && !Array.isArray(record.read_window)
        ? record.read_window as Record<string, unknown>
        : {}
      const userSegments = record.content
        .split(/\n(?=(?:user|assistant):\s)/i)
        .filter(segment => /^user:\s/i.test(segment))
      return userSegments
        .filter(segment => taskTokens.size === 0 || tokenOverlap(contentTokens(segment), taskTokens) >= 2)
        .slice(0, 3).map((segment, index) => ({
        evidence_key: `${record.id}:${String(window.offset ?? 0)}:${index}`,
        memory_id: record.id as string,
        source_ref: typeof source.ref === 'string' ? source.ref : undefined,
        source_refs: Array.isArray(record.source_refs)
          ? record.source_refs.filter((ref): ref is string => typeof ref === 'string').slice(0, 3)
          : [],
        source_date: typeof temporal.event_time === 'string' ? temporal.event_time : undefined,
        speaker: 'user',
        excerpt: segment.slice(0, 600),
      }))
    } catch {
      return []
    }
  })
  const unique = [...new Map([...searchHits, ...readHits]
    .filter(hit => hit.evidence_key)
    .map(hit => [hit.evidence_key, hit])).values()]
  return unique.length > 0
    ? `Exact user evidence preserved from child MemorySearch and MemoryRead tool results.\n${JSON.stringify(unique.slice(0, 16))}`
    : ''
}

function contentTokens(value: string): Set<string> {
  return new Set(value.toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .split(/\s+/)
    .filter(token => token.length >= 4 && !EVIDENCE_STOP_WORDS.has(token)))
}

function tokenOverlap(left: Set<string>, right: Set<string>): number {
  return [...left].filter(token => right.has(token)).length
}

const EVIDENCE_STOP_WORDS = new Set([
  'about', 'after', 'again', 'also', 'already', 'before', 'could', 'each', 'from', 'have', 'memory',
  'report', 'source', 'their', 'there', 'these', 'they', 'this', 'those', 'user', 'what', 'when', 'where',
  'which', 'with', 'would', 'your',
])

function resolveAllowedTools(names: readonly string[], availableTools: readonly Tool[]): Tool[] {
  const resolved: Tool[] = []
  for (const name of names) {
    const tool = findToolByName(availableTools, name)
    if (tool && tool.name !== FORK_SUBAGENT_TOOL_NAME && !resolved.includes(tool)) resolved.push(tool)
  }
  return resolved
}

function buildDelegationMessage(
  prompt: string,
  objective: string,
  contextRefs: readonly string[],
  contextPrelude: string,
): string {
  return [
    `Objective: ${objective}`,
    `Task: ${prompt}`,
    contextRefs.length > 0 ? `Context references:\n${contextRefs.map(ref => `- ${ref}`).join('\n')}` : '',
    contextPrelude ? `<delegated_context>\n${contextPrelude}\n</delegated_context>` : '',
    'Return only the result needed by the parent. State missing information explicitly.',
  ].filter(Boolean).join('\n')
}

function defaultSubagentSystemPrompt(): string {
  return [
    'You are an isolated subagent executing one bounded delegated task.',
    'Use only the tools provided to you. Do not attempt to spawn another agent.',
    'Do not answer broader user goals or take ownership of the parent task.',
    'Keep your final result concise, factual, and explicit about uncertainty.',
  ].join('\n')
}
