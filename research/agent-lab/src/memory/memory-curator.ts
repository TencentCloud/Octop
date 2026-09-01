import { randomUUID } from 'node:crypto'

import { runAgentLoop } from '../core/agent-loop.js'
import { CompactingContextManager } from '../core/context-compression.js'
import {
  createSystemMessage,
  createUserMessage,
  type AgentEvent,
  type Message,
} from '../core/messages.js'
import type { AgentModelLike } from '../core/model-stream.js'
import { createPermissionContext, PermissionBehavior } from '../core/permissions.js'
import type { Tool } from '../core/tool.js'

export type CuratorAction = 'write' | 'defer' | 'retrieve' | 'discard'

export type CuratorDecision = {
  action: CuratorAction
  reason: string
  memory_ids?: string[]
  missing?: string[]
}

export type MemoryCuratorResult = {
  status: 'completed' | 'max_turns_exceeded'
  decision: CuratorDecision | null
  events: AgentEvent[]
}

export async function runMemoryCurator({
  model,
  transcript,
  memoryTools,
  memoryRoot,
  maxTurns,
  maxContextChars,
}: {
  model: AgentModelLike
  transcript: readonly Message[]
  memoryTools: readonly Tool[]
  memoryRoot: string
  maxTurns: number
  maxContextChars: number
}): Promise<MemoryCuratorResult> {
  const subagentId = randomUUID()
  const tools = memoryTools.filter(tool => [
    'MemorySearch',
    'MemoryRead',
    'MemoryCreate',
    'MemoryUpdate',
    'MemoryDeleteDerived',
  ].includes(tool.name))
  const permissionContext = createPermissionContext({
    cwd: memoryRoot,
    readableRoots: [memoryRoot],
    writableRoots: [memoryRoot],
    toolRules: Object.fromEntries(tools.map(tool => [tool.name, PermissionBehavior.ALLOW])),
  })
  const forkMessages = transcript.filter(message => message.role !== 'system')
  const startEvent: AgentEvent = {
    type: 'subagent_start',
    turn: 0,
    subagentId,
    kind: 'memory_curator',
    objective: 'Form durable, sourced memories from the completed parent turn.',
  }

  const result = await runAgentLoop({
    model,
    tools,
    permissionContext,
    maxTurns,
    contextManager: new CompactingContextManager({
      maxChars: maxContextChars,
      preserveRecentChars: Math.floor(maxContextChars * 0.45),
      summaryMaxChars: Math.floor(maxContextChars * 0.2),
    }),
    messages: [
      createSystemMessage(CURATOR_SYSTEM_PROMPT),
      ...forkMessages,
      createUserMessage([
        'The parent turn is complete. Curate only durable information from this transcript.',
        'Use memory tools when writing or updating. Finish with one JSON decision object and no Markdown.',
      ].join('\n')),
    ],
  })
  const childToolCalls = result.events
    .filter(event => event.type === 'tool_call_start')
    .map(event => event.type === 'tool_call_start' ? event.toolName : '')
  const endEvent: AgentEvent = {
    type: 'subagent_end',
    turn: 0,
    subagentId,
    kind: 'memory_curator',
    status: result.status,
    childTurns: result.events.filter(event => event.type === 'model_turn_start').length,
    childToolCalls,
  }

  return {
    status: result.status,
    decision: parseCuratorDecision(result.output),
    events: [startEvent, ...result.events, endEvent],
  }
}

const CURATOR_SYSTEM_PROMPT = [
  'You are an isolated Memory Curator Subagent.',
  'Your job is memory formation, not answering the user.',
  'Choose among write, defer, retrieve, or discard before acting.',
  'write: durable information is complete and useful across future conversations.',
  'defer: information may be useful but a reference, time, entity, or outcome is incomplete. Write a deferred record that names what is missing.',
  'retrieve: search and read existing memories before deciding whether to create or update.',
  'discard: information is transient, duplicated, derivable from project files, or unsupported.',
  'Store raw conversational claims as kind=evidence. Evidence is immutable.',
  'Store dated actions as kind=event with temporal.event_time or temporal.valid_from.',
  'Store current conclusions as kind=state with source_refs pointing to supporting evidence or events.',
  'Store stable knowledge and reusable experience as kind=topic.',
  'Never turn assumptions, assistant suggestions, or missing search results into facts.',
  'Before creating a memory, use MemorySearch and MemoryRead to avoid duplicates and to identify updates.',
  'Never use MemoryDelete; only MemoryDeleteDerived is available, and only for incorrect derived records.',
  'Every create/update must carry exact source refs from the transcript or an existing memory.',
  'Finish with JSON: {"action":"write|defer|retrieve|discard","reason":"...","memory_ids":[],"missing":[]}',
].join('\n')

function parseCuratorDecision(output: string | null): CuratorDecision | null {
  if (!output) return null
  try {
    const parsed = JSON.parse(output) as Partial<CuratorDecision>
    if (!parsed.action || !['write', 'defer', 'retrieve', 'discard'].includes(parsed.action)) return null
    if (typeof parsed.reason !== 'string' || !parsed.reason.trim()) return null
    return {
      action: parsed.action,
      reason: parsed.reason.trim(),
      memory_ids: Array.isArray(parsed.memory_ids)
        ? parsed.memory_ids.filter((value): value is string => typeof value === 'string')
        : [],
      missing: Array.isArray(parsed.missing)
        ? parsed.missing.filter((value): value is string => typeof value === 'string')
        : [],
    }
  } catch {
    return null
  }
}
