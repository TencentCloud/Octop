import { runAgentLoop, type RunAgentLoopResult } from '../core/agent-loop.js'
import type { AgentModelLike } from '../core/model-stream.js'
import { InMemoryChildSidechainStore } from '../core/child-sidechain.js'
import { CompactingContextManager } from '../core/context-compression.js'
import { createForkSubagentTool } from '../core/fork-subagent.js'
import type { ToolHooks } from '../core/hooks.js'
import { createPermissionContext } from '../core/permissions.js'
import { InMemoryResultLedgerStore } from '../core/result-ledger.js'
import { createSystemMessage, type Message } from '../core/messages.js'
import { executeToolCall } from '../core/tool-execution.js'
import type { ToolCall } from '../core/messages.js'
import { createTodoWriteTool, InMemoryTodoStore } from '../core/todo.js'
import { loadMemoryAgentConfig } from './config.js'
import { MemoryContextManager } from './context-manager.js'
import { FileMemoryStore } from './store.js'
import { createMemoryTools, MEMORY_TOOL_RULES } from './tools.js'
import { createEvidenceReaderSubagentTool } from './evidence-reader-subagent.js'
import { createCompileEvidenceTool } from './compile-evidence-tool.js'
import { planEvidenceRoute, type EvidenceRoutePlan } from './evidence-route-planner.js'
import type { EvidenceDecision, StructuredEvidenceReport } from './evidence-report.js'
import { runMemoryCurator } from './memory-curator.js'
import { searchMemoryCatalog } from './memory-catalog.js'
import type { MemoryRecord } from './types.js'

export async function createMemoryAgent(configPath: string) {
  const config = await loadMemoryAgentConfig(configPath)
  const store = new FileMemoryStore(config.memoryRoot)
  await store.initialize()
  const tools = createMemoryTools(store)
  const permissionContext = createPermissionContext({
    cwd: config.memoryRoot,
    readableRoots: [config.memoryRoot],
    writableRoots: [config.memoryRoot],
    toolRules: MEMORY_TOOL_RULES,
  })
  const memoryContextManager = new MemoryContextManager(store, config.context)
  const contextManager = new CompactingContextManager({
    ...config.compression,
    delegate: memoryContextManager,
  })
  const orchestratorContextManager = new CompactingContextManager(config.compression)
  const sidechains = new InMemoryChildSidechainStore()
  const results = new InMemoryResultLedgerStore()
  const todos = new InMemoryTodoStore()
  const todoTool = createTodoWriteTool({ store: todos })

  return {
    config,
    store,
    tools,
    permissionContext,
    contextManager,
    sidechains,
    results,
    todos,
    async run(
      model: AgentModelLike,
      messages: readonly Message[],
      maxTurns = 10,
      hooks?: ToolHooks,
      options?: {
        forceEvidenceReader?: boolean
        questionType?: string
        evidenceObjective?: string
        enforceNoAnswerGuard?: boolean
        curateAfterRun?: boolean
        evidenceReaderMode?: 'bundle' | 'legacy' | 'off'
        maxToolCallsPerTurn?: number
        evidenceReaderMaxTurns?: number
        finalAnswerWithoutTools?: boolean
        reserveFinalAnswerTurn?: boolean
        evidencePlanner?: boolean
        orchestratorOnly?: boolean
        parentMode?: 'full' | 'orchestrator' | 'orchestrator-ledger'
        forkSubagentMaxTurns?: number
        memoryCatalog?: boolean
        structuredEvidenceResults?: boolean
        runtimeProfile?: 'current' | 'v51'
      },
    ): Promise<RunAgentLoopResult> {
      const runtimeProfile = options?.runtimeProfile ?? 'current'
      const originalRequest = evidenceQueryFromMessages(messages)
      const subagentTool = createEvidenceReaderSubagentTool({
        model,
        memoryTools: tools,
        contextManager,
        memoryRoot: config.memoryRoot,
        store,
        sidechainStore: sidechains,
      })
      const ledgerMode = options?.parentMode === 'orchestrator-ledger'
      const genericSubagentTool = createForkSubagentTool({
        model,
        availableTools: tools.filter(tool =>
          ['MemorySearch', 'MemoryRead', 'MemoryEvidenceBundle'].includes(tool.name),
        ),
        sidechainStore: sidechains,
        resultLedger: results,
        resultMode: ledgerMode ? 'ledger' : 'inline',
        defaultMaxTurns: options?.forkSubagentMaxTurns ?? 6,
        structuredEvidence: options?.structuredEvidenceResults === true,
        evidenceCompatibility: runtimeProfile,
        resolveContextPrelude: (contextRefs, prompt) => buildForkEventPrelude(
          store,
          contextRefs,
          `${originalRequest.query}\n${prompt}`,
        ),
        systemPrompt: options?.structuredEvidenceResults === true
          ? structuredEvidenceSubagentSystemPrompt(runtimeProfile)
          : undefined,
      })
      const compileEvidenceTool = createCompileEvidenceTool({
        model,
        resultLedger: results,
        sidechainStore: sidechains,
        taskContext: originalRequest.query,
        profile: runtimeProfile,
      })
      permissionContext.toolRules.ForkEvidenceReader = 'allow'
      permissionContext.toolRules.ForkSubagent = 'allow'
      permissionContext.toolRules.CompileEvidence = 'allow'
      permissionContext.toolRules.TodoWrite = 'allow'
      const runTools = [...tools, todoTool, genericSubagentTool, subagentTool]
      const parentTools = ledgerMode
        ? [todoTool, genericSubagentTool, compileEvidenceTool]
        : options?.parentMode === 'orchestrator'
          ? [todoTool, genericSubagentTool]
          : runTools
      let routedMessages = [...messages]
      let routedEvents: RunAgentLoopResult['events'] = []
      if (options?.memoryCatalog === true) {
        const request = evidenceQueryFromMessages(messages)
        const catalog = await searchMemoryCatalog(store, request.query, {
          maxSources: 16,
          maxEventsPerSource: 1,
          maxChars: 7_000,
        })
        const catalogMessage: Message = {
          role: 'system',
          content: [
            '<memory_catalog>',
            JSON.stringify(catalog),
            '</memory_catalog>',
            'This catalog is a bounded navigation snapshot, not answer evidence. Use its memory IDs and source refs to plan complementary ForkSubagent tasks. Do not search the catalog repeatedly.',
          ].join('\n'),
        }
        const lastUserIndex = routedMessages.findLastIndex(message => message.role === 'user')
        routedMessages.splice(lastUserIndex >= 0 ? lastUserIndex : routedMessages.length, 0, catalogMessage)
      }
      let evidenceOutcome: {
        derived_decision?: EvidenceDecision | null
        report?: StructuredEvidenceReport | null
        report_valid?: boolean
      } | null = null
      let routePlan: EvidenceRoutePlan | null = null
      const plannerEnabled = options?.evidencePlanner === true
      const shouldRouteEvidence = (options?.forceEvidenceReader === true || plannerEnabled) &&
        options.evidenceReaderMode !== 'off'

      if (shouldRouteEvidence) {
        const evidenceRequest = evidenceQueryFromMessages(messages)
        routePlan = plannerEnabled
          ? await planEvidenceRoute(store, evidenceRequest.query, evidenceRequest.referenceDate)
          : null
        const toolCall: ToolCall = {
          id: `route_evidence_${Date.now()}`,
          name: 'ForkEvidenceReader',
          input: {
            query: evidenceRequest.query,
            reference_date: evidenceRequest.referenceDate,
            objective: routePlan?.objective ?? options.evidenceObjective ?? defaultEvidenceObjective(options.questionType),
            max_turns: Math.min(options?.evidenceReaderMaxTurns ?? routePlan?.max_turns ?? 5, routePlan?.max_turns ?? 8),
            use_bundle: options.evidenceReaderMode !== 'legacy',
            preferred_role: routePlan?.preferred_role ?? (options.questionType === 'single-session-assistant' ? 'assistant' : 'user'),
            profiles: routePlan?.profiles,
            risk_flags: routePlan?.risk_flags,
            operations: routePlan?.operations,
            required_facets: routePlan?.required_facets,
            evidence_preview: routePlan?.preview,
          },
        }
        const assistant = {
          role: 'assistant' as const,
          content: 'Delegating evidence organization before answering.',
          tool_calls: [toolCall],
        }
        routedMessages.push(assistant)
        const routed = await executeToolCall({
          toolCall,
          tools: runTools,
          permissionContext,
          messages: routedMessages,
          turn: 0,
          hooks,
        })
        routedMessages.push(routed.message, ...routed.contextMessages)
        evidenceOutcome = parseEvidenceOutcome(routed.message.content)
        if (options.finalAnswerWithoutTools || options.orchestratorOnly || plannerEnabled) {
          routedMessages.push({
            role: 'user',
            content: [
              'The evidence phase is complete and no tools are available in the answer phase.',
              'Answer the original question directly from the Evidence Reader result above.',
              'Do not emit tool-call syntax, XML, JSON, or a request to search memory.',
              ...answerPhaseInstructions(routePlan),
              `Question: ${evidenceRequest.query}`,
              `Reference date: ${evidenceRequest.referenceDate}`,
            ].join('\n'),
          })
        }
        if (evidenceOutcome?.derived_decision?.kind === 'pending_action_count') {
          const decision = evidenceOutcome.derived_decision
          routedMessages.push({
            role: 'system',
            content: [
              'Validated evidence answer contract:',
              `The evidence compiler counted ${decision.count} distinct pending actions across ${decision.entity_count} physical entities.`,
              'The question asks for actions matching its verbs. Answer with the action count, not the deduplicated entity count.',
              `Required count: ${decision.count}. Action IDs: ${decision.action_ids.join(', ')}.`,
            ].join('\n'),
          })
        }
        routedEvents = [
          { type: 'assistant_message', turn: 0, message: assistant },
          ...routed.events,
        ]
      }

      const result = await runAgentLoop({
        model,
        tools: shouldRouteEvidence && (options?.finalAnswerWithoutTools || options?.orchestratorOnly || plannerEnabled)
          ? []
          : parentTools,
        permissionContext,
        contextManager: options?.parentMode === 'orchestrator' || ledgerMode
          ? orchestratorContextManager
          : contextManager,
        messages: routedMessages,
        maxTurns,
        maxToolCallsPerTurn: options?.maxToolCallsPerTurn,
        reserveFinalAnswerTurn: options?.reserveFinalAnswerTurn,
        answerAfterToolNames: ledgerMode ? ['CompileEvidence'] : undefined,
        toolCallLimits: ledgerMode
          ? { TodoWrite: 1, ForkSubagent: 2, CompileEvidence: 1 }
          : undefined,
        toolPrerequisites: ledgerMode
          ? { CompileEvidence: ['ForkSubagent'] }
          : undefined,
        requireAnyToolBeforeAnswer: ledgerMode ? ['ForkSubagent'] : undefined,
        requireToolBeforeAnswerAfter: ledgerMode
          ? [{ requiredTool: 'CompileEvidence', triggerTool: 'ForkSubagent', triggerCount: 1 }]
          : undefined,
        hooks,
      })
      let combined = { ...result, events: [...routedEvents, ...result.events] }
      const coverageFollowUp = runtimeProfile !== 'v51' && ledgerMode && options?.structuredEvidenceResults === true
        ? compileCoverageFollowUp(combined.messages)
        : null
      if (coverageFollowUp) {
        const followUpResult = await runAgentLoop({
          model,
          tools: [genericSubagentTool, compileEvidenceTool],
          permissionContext,
          contextManager: orchestratorContextManager,
          messages: [...combined.messages, createSystemMessage([
            'The first evidence compilation found concrete unresolved memory sources. Do one bounded coverage repair before answering.',
            `Call ForkSubagent once with context_refs set to exactly these unresolved source refs: ${coverageFollowUp.sourceRefs.join(', ')}.`,
            'The delegated prompt must inspect only those sources for missing task-relevant facts, exclusions, conflicts, or updates. Use MemoryRead, MemorySearch, and MemoryEvidenceBundle as needed.',
            'After the ForkSubagent result, call CompileEvidence once. Include the new result ID; the compiler will also recover prior ledger IDs from the conversation.',
            'Do not broaden the search and do not answer until the second CompileEvidence call completes.',
          ].join('\n'))],
          maxTurns: 4,
          maxToolCallsPerTurn: 1,
          reserveFinalAnswerTurn: true,
          answerAfterToolNames: ['CompileEvidence'],
          toolCallLimits: { ForkSubagent: 1, CompileEvidence: 1 },
          toolPrerequisites: { CompileEvidence: ['ForkSubagent'] },
          requireAnyToolBeforeAnswer: ['ForkSubagent'],
          requireToolBeforeAnswerAfter: [{ requiredTool: 'CompileEvidence', triggerTool: 'ForkSubagent', triggerCount: 1 }],
          hooks,
        })
        combined = {
          ...followUpResult,
          events: [...combined.events, ...followUpResult.events],
        }
      }
      let finalResult = applyEvidenceAnswerGuard(
        combined,
        evidenceOutcome,
        options?.enforceNoAnswerGuard === true || routePlan?.enforce_no_answer_guard === true,
      )
      finalResult = applyCompileEvidenceAnswerGuard(finalResult, originalRequest.query, runtimeProfile)

      if (
        finalResult.status === 'completed' &&
        (options?.curateAfterRun ?? config.curator.enabled)
      ) {
        try {
          const curation = await runMemoryCurator({
            model,
            transcript: combined.messages,
            memoryTools: tools,
            memoryRoot: config.memoryRoot,
            maxTurns: config.curator.maxTurns,
            maxContextChars: config.curator.maxContextChars,
          })
          finalResult = {
            ...finalResult,
            events: [...finalResult.events, ...curation.events],
          }
        } catch (error) {
          finalResult = {
            ...finalResult,
            events: [...finalResult.events, {
              type: 'subagent_error',
              turn: 0,
              subagentId: 'memory-curator',
              kind: 'memory_curator',
              error: error instanceof Error ? error.message : String(error),
            }],
          }
        }
      }

      return finalResult
    },
  }
}

function structuredEvidenceSubagentSystemPrompt(profile: 'current' | 'v51' = 'current'): string {
  return [
    'You are an isolated memory evidence subagent executing one bounded delegated task.',
    'Use only the read-only tools provided. Memory catalog summaries are navigation hints, not final evidence.',
    'The delegated_context may contain bounded Event Ledger excerpts already loaded from immutable memory, with exact speaker and turn refs. Treat those excerpts as sourced evidence; use Raw Memory only for missing context or status resolution.',
    'Do not exhaustively page through every referenced Raw Memory when the preloaded excerpts already cover the task facets. Prioritize relevant evidence and reserve the final turn for the structured report.',
    'Discovery discipline: use meaningfully different paraphrases, including one broad conceptual query that does not merely repeat the question nouns. After MemorySearch reveals a new relevant source, read that source before issuing another search. Stop expanding only after two diverse searches add no relevant source.',
    'MemoryRead is paginated. Inspect read_window.has_more and follow next_offset when the relevant passage may be later in the source. Do not mark an assigned source covered while material windows remain unread.',
    'Read the relevant Event Ledger or Raw Memory records before including a candidate.',
    'First perform an atomic candidate census, then resolve status. Split every explicit task-relevant clause into its own candidate before deduplication; never omit a clause merely because a nearby clause appears inconsistent.',
    'Treat the unit requested by the task as the candidate identity: it may be an entity, event, action, relation, or state.',
    'Keep distinct candidates separate until source, entity, predicate/action, event, and time evidence justify merging them. Distinct actions on the same entity are distinct candidates when the task counts actions.',
    'For exchanges or replacements, the original item being returned and the replacement item being collected are distinct obligation endpoints when both actions are explicitly pending. Do not collapse them into one product mention.',
    'Preserve predicate fidelity. A related role such as participating, contributing, supporting, or co-organizing does not by itself entail leading, owning, preferring, or completing the task predicate.',
    'Do not replace an explicit user predicate with a weaker or conflicting assistant paraphrase from an adjacent turn. Preserve both as separate sourced claims when they conflict.',
    'Resolve same-session discourse ellipsis when one unique entity is explicitly active immediately before and after the event and the conversation remains on that entity. Mark it as a discourse-supported relation, not an explicit quote. Do not use weak cross-session topic similarity for this bridge.',
    'Explicit current obligations such as need to return, still need to pick up, or remains pending outrank inferred completion from nearby words such as exchanged or replaced. Close an action only with explicit completed, returned, collected, cancelled, or equivalent evidence.',
    'Every candidate must preserve both memory_ids and source_refs. State exclusions and uncertainty explicitly.',
    'Keep the JSON under 4200 characters. Each claim must be at most 160 characters. Omit reason unless essential, never repeat evidence quotes, and add no prose outside the JSON.',
    'Represent one task-relevant counting unit once. Put repeated mentions of that same unit in source_refs and memory_ids; never merge different predicates or actions merely because they share an entity.',
    'Return only one JSON object with this schema:',
    ...(profile === 'v51'
      ? [
          '{"schema_version":"1.0","task":"...","candidates":[{"id":"...","claim":"...","decision":"include|exclude|uncertain","source_refs":["..."],"memory_ids":["..."],"source_date":"optional","event_time":"optional","duplicate_of":"optional","reason":"optional"}],"covered_memory_ids":["..."],"covered_source_refs":["..."],"unexplored_source_refs":["..."],"coverage_status":"complete|incomplete|uncertain","conflicts":["..."],"missing_information":["..."]}',
          'Use coverage_status=complete only after every assigned source was inspected and repeated diverse searches found no new relevant source. Budget exhaustion or unread windows require incomplete or uncertain coverage. Do not answer the broader user question.',
        ]
      : [
          '{"schema_version":"1.1","task":"...","candidates":[{"id":"...","claim":"...","decision":"include|exclude|uncertain","source_refs":["..."],"memory_ids":["..."],"source_date":"optional","event_time":"optional","duplicate_of":"optional","reason":"optional"}],"coverage":{"inspected_source_refs":["..."],"unresolved_source_refs":["..."],"stop_reason":"assigned_scope_exhausted|relevant_sources_exhausted|two_searches_no_new_source|budget_exhausted|unresolved_sources|unread_memory|not_applicable"},"conflicts":["..."],"missing_information":["..."]}',
          'Use assigned_scope_exhausted only after every source assigned by the parent was inspected. Use two_searches_no_new_source only after two meaningfully different searches found no new relevant source. Budget or unread windows must remain unresolved. Do not answer the broader user question.',
        ]),
  ].join('\n')
}

async function buildForkEventPrelude(
  store: FileMemoryStore,
  contextRefs: readonly string[],
  prompt: string,
): Promise<string> {
  const resolvedSources = await Promise.all(contextRefs.map(async ref => {
    let direct: MemoryRecord | null = null
    try {
      direct = await store.read(ref)
    } catch {
      // Source and turn refs are navigation references, not memory IDs.
    }
    if (direct) return direct.source.ref
    const sourceRef = ref.replace(/#turn-\d+.*$/i, '')
    const sourceRecords = await store.findBySourcePrefix(sourceRef, 1)
    return sourceRecords[0]?.source.ref ?? null
  }))
  const sources = new Set(resolvedSources.filter((source): source is string => Boolean(source)))
  if (sources.size === 0) return ''
  const hits = await store.search({ query: prompt, kinds: ['event'], limit: 50 })
  const relevantHits = hits.filter(hit => sources.has(hit.source_ref))
  const bestBySource = new Map<string, typeof relevantHits[number]>()
  for (const hit of relevantHits) {
    if (!bestBySource.has(hit.source_ref)) bestBySource.set(hit.source_ref, hit)
  }
  const topHits = [...bestBySource.values()].slice(0, 16)
  const recordsBySource = new Map<string, Awaited<ReturnType<FileMemoryStore['findBySourcePrefix']>>>()
  for (const source of sources) {
    recordsBySource.set(source, (await store.findBySourcePrefix(source, 50))
      .filter(record => record.tags.includes('memory-layer:event')))
  }
  const selectedRecords: MemoryRecord[] = []
  const seen = new Set<string>()
  const addRecord = (record: MemoryRecord | undefined) => {
    if (!record || seen.has(record.id)) return
    seen.add(record.id)
    selectedRecords.push(record)
  }
  for (const record of [...recordsBySource.values()].flat()) {
    if (record.tags.includes('speaker:user') && explicitlyMatchesRequestedAction(record.content, prompt)) addRecord(record)
  }
  for (const hit of topHits) {
    addRecord((recordsBySource.get(hit.source_ref) ?? []).find(record => record.id === hit.id))
  }
  for (const hit of topHits) {
    const hitTurn = turnIndex(hit.source_refs)
    const sourceRecords = recordsBySource.get(hit.source_ref) ?? []
    const neighbors = sourceRecords
      .filter(record => hitTurn === null || Math.abs((turnIndex(record.source_refs) ?? 10_000) - hitTurn) <= 1)
      .sort((left, right) => speakerRank(left.tags) - speakerRank(right.tags))
    for (const record of neighbors) addRecord(record)
  }
  for (const hit of relevantHits) {
    addRecord((recordsBySource.get(hit.source_ref) ?? []).find(record => record.id === hit.id))
  }
  const selected = []
  for (const record of selectedRecords) {
    const item = {
      memory_id: record.id,
      source_ref: record.source.ref,
      turn_ref: record.source_refs.find(ref => ref.includes('#turn-')),
      speaker: record.tags.find(tag => tag.startsWith('speaker:'))?.slice('speaker:'.length) ?? 'unknown',
      source_date: record.temporal?.event_time,
      excerpt: compactPreludeText(record.content, 650),
    }
    if (JSON.stringify([...selected, item]).length > 9_000) break
    selected.push(item)
  }
  if (selected.length === 0) return ''
  return [
    'Bounded Event Ledger excerpts preloaded from immutable memory. They are sourced evidence with exact speaker and turn attribution.',
    JSON.stringify(selected),
  ].join('\n')
}

function explicitlyMatchesRequestedAction(content: string, prompt: string): boolean {
  const requested = requestedActionNames(prompt)
  if (requested.length === 0) return false
  const normalized = normalizeActionText(content)
  return requested.some(action => {
    const phrase = action.replace(/\s+/g, '\\s*')
    return new RegExp(`\\b(?:still\\s+)?(?:need(?:s|ed)?|have|has)\\s+to\\s+${phrase}\\b`, 'i').test(normalized) ||
      new RegExp(`\\b(?:haven't|have not|hasn't|has not)\\s+(?:had\\s+)?(?:a\\s+)?chance\\s+to\\s+${phrase}\\b`, 'i').test(normalized)
  })
}

function requestedActionNames(value: string): string[] {
  const normalized = normalizeActionText(value)
  return ['pick up', 'return', 'collect', 'drop off', 'send back'].filter(action => normalized.includes(action))
}

function normalizeActionText(value: string): string {
  return value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\bpickup\b/g, 'pick up').replace(/\s+/g, ' ').trim()
}

function turnIndex(sourceRefs: readonly string[]): number | null {
  const match = sourceRefs.find(ref => ref.includes('#turn-'))?.match(/#turn-(\d+)/)
  return match ? Number(match[1]) : null
}

function speakerRank(tags: readonly string[]): number {
  return tags.includes('speaker:user') ? 0 : tags.includes('speaker:assistant') ? 1 : 2
}

function compactPreludeText(value: string, maxChars: number): string {
  const compact = value.replace(/\s+/g, ' ').trim()
  return compact.length <= maxChars ? compact : `${compact.slice(0, maxChars - 3).trimEnd()}...`
}

function parseEvidenceOutcome(content: string): {
  derived_decision?: EvidenceDecision | null
  report?: StructuredEvidenceReport | null
  report_valid?: boolean
} | null {
  try {
    const parsed = JSON.parse(content) as unknown
    return parsed && typeof parsed === 'object'
      ? parsed as {
          derived_decision?: EvidenceDecision | null
          report?: StructuredEvidenceReport | null
          report_valid?: boolean
        }
      : null
  } catch {
    return null
  }
}

function applyEvidenceAnswerGuard(
  result: RunAgentLoopResult,
  outcome: {
    derived_decision?: EvidenceDecision | null
    report?: StructuredEvidenceReport | null
    report_valid?: boolean
  } | null,
  enforceNoAnswerGuard: boolean,
): RunAgentLoopResult {
  const report = outcome?.report
  if (
    enforceNoAnswerGuard &&
    report?.answerability === 'no_answer' &&
    (outcome?.report_valid === true || report.missing_information.length > 0)
  ) {
    return replaceFinalAnswer(result, correctedNoAnswer(report), {
      decisionKind: 'no_answer',
      expected: 'no_answer',
      observed: result.output?.trim() ? 'answer_or_abstention' : null,
    })
  }

  const decision = outcome?.derived_decision
  if (!decision) return result
  const observed = extractStatedCount(result.output ?? '')
  if (
    decision.kind === 'pending_action_count' &&
    result.status === 'completed' &&
    observed === decision.count
  ) return result

  const corrected = correctedEvidenceAnswer(decision, report ?? null)
  return replaceFinalAnswer(result, corrected, {
    decisionKind: decision.kind,
    expected: decision.count,
    observed,
  })
}

export function applyCompileEvidenceAnswerGuard(
  result: RunAgentLoopResult,
  query: string,
  profile: 'current' | 'v51' = 'current',
): RunAgentLoopResult {
  if (result.status !== 'completed') return result
  const packet = latestCompileEvidencePacket(result.messages)
  if (!packet) return result
  const contract = packet.answer_contract
  const projection = contract && typeof contract === 'object' && !Array.isArray(contract)
    ? contract as Record<string, unknown>
    : null
  if (typeof packet.state_answer === 'string' && packet.state_answer.trim()) {
    const answer = packet.state_answer.trim()
    return replaceFinalAnswer(
      result,
      `${answer}. This is the latest dated state explicitly stated by the user in the compiled evidence.`,
      { decisionKind: 'compile_evidence_latest_state', expected: answer, observed: result.output?.trim() || null },
    )
  }
  if (/\bwhere\s+(?:did|was|is|are|were|do|does)\b|\bwhich\s+(?:store|location|retailer|place)\b/i.test(query) && typeof packet.discourse_answer === 'string' && packet.discourse_answer.trim()) {
    const answer = packet.discourse_answer.trim()
    return replaceFinalAnswer(
      result,
      `${answer}. This is the uniquely supported same-session location inferred from the surrounding discourse; the event sentence itself does not repeat the store name.`,
      { decisionKind: 'compile_evidence_discourse_answer', expected: answer, observed: result.output?.trim() || null },
    )
  }
  if (profile === 'v51' && isCountQuestion(query) && packet.count_contract === 'deterministic') {
    const included = Array.isArray(packet.included)
      ? packet.included.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
      : []
    const expected = typeof packet.included_count === 'number'
      ? packet.included_count
      : typeof packet.derived_count === 'number'
        ? packet.derived_count
        : included.length > 0 ? included.length : null
    if (expected !== null) {
      const observed = extractStatedCount(result.output ?? '')
      if (observed !== expected) {
        const claims = included.flatMap(item => typeof item.claim === 'string' ? [item.claim] : [])
        const label = isActionCountQuestion(query) ? 'distinct matching actions' : 'distinct supported items'
        const answer = claims.length > 0
          ? `There are ${expected} ${label}: ${claims.join('; ')}`
          : `There are ${expected} ${label}.`
        return replaceFinalAnswer(result, answer, {
          decisionKind: isActionCountQuestion(query) ? 'compile_evidence_action_count' : 'compile_evidence_count',
          expected,
          observed,
        })
      }
    }
    return result
  }
  if (
    isCountQuestion(query) &&
    packet.count_contract === 'deterministic' &&
    packet.coverage_status === 'complete' &&
    projection?.operation === 'count' &&
    projection.projection_status === 'committed'
  ) {
    const included = Array.isArray(packet.included)
      ? packet.included.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
      : []
    const expected = typeof packet.included_count === 'number'
      ? packet.included_count
      : typeof packet.derived_count === 'number'
        ? packet.derived_count
        : included.length > 0 ? included.length : null
    if (expected !== null) {
      const observed = extractStatedCount(result.output ?? '')
      const contracted = typeof projection.final_answer === 'string' ? projection.final_answer.trim() : ''
      const contractedCount = extractContractedCardinality(contracted)
      if (observed !== expected && contractedCount === expected) {
        return replaceFinalAnswer(result, contracted, {
          decisionKind: isActionCountQuestion(query) ? 'compile_evidence_action_count' : 'compile_evidence_count',
          expected,
          observed,
        })
      }
    }
  }
  if (projection) {
    if (
      projection.projection_status === 'committed' &&
      projection.operation !== 'count' &&
      projection.operation !== 'preference' &&
      projection.operation !== 'recommendation' &&
      typeof projection.final_answer === 'string' &&
      projection.final_answer.trim()
    ) {
      const answer = projection.final_answer.trim()
      return replaceFinalAnswer(result, answer, {
        decisionKind: 'compile_evidence_answer_contract',
        expected: answer,
        observed: result.output?.trim() || null,
      })
    }
  }
  return result
}

function latestCompileEvidencePacket(messages: readonly Message[]): Record<string, unknown> | null {
  const envelope = latestCompileEvidenceEnvelope(messages)
  if (!envelope) return null
  if (envelope.evidence_packet && typeof envelope.evidence_packet === 'object' && !Array.isArray(envelope.evidence_packet)) {
    return envelope.evidence_packet as Record<string, unknown>
  }
  return typeof envelope.evidence_packet === 'string' ? parseLooseJsonObject(envelope.evidence_packet) : null
}

function latestCompileEvidenceEnvelope(messages: readonly Message[]): Record<string, unknown> | null {
  const toolMessage = [...messages].reverse().find(message => message.role === 'tool' && message.tool_name === 'CompileEvidence')
  if (!toolMessage) return null
  try {
    const envelope = JSON.parse(toolMessage.content) as unknown
    return envelope && typeof envelope === 'object' && !Array.isArray(envelope)
      ? envelope as Record<string, unknown>
      : null
  } catch {
    return null
  }
}

export function compileCoverageFollowUp(messages: readonly Message[]): { sourceRefs: string[] } | null {
  const envelope = latestCompileEvidenceEnvelope(messages)
  if (!envelope) return null
  const packet = envelope.evidence_packet && typeof envelope.evidence_packet === 'object' && !Array.isArray(envelope.evidence_packet)
    ? envelope.evidence_packet as Record<string, unknown>
    : null
  const coverage = envelope.cross_source_coverage && typeof envelope.cross_source_coverage === 'object' && !Array.isArray(envelope.cross_source_coverage)
    ? envelope.cross_source_coverage as Record<string, unknown>
    : packet?.coverage_decision && typeof packet.coverage_decision === 'object' && !Array.isArray(packet.coverage_decision)
      ? packet.coverage_decision as Record<string, unknown>
      : null
  if (packet?.coverage_status !== 'incomplete' && coverage?.status !== 'incomplete') return null
  const refs = [
    ...(Array.isArray(coverage?.unresolved_source_refs) ? coverage.unresolved_source_refs : []),
    ...(Array.isArray(packet?.unexplored_sources) ? packet.unexplored_sources : []),
  ].filter((ref): ref is string => typeof ref === 'string' && ref.trim().length > 0)
  const sourceRefs = [...new Set(refs.map(ref => ref.trim()))].slice(0, 4)
  return sourceRefs.length > 0 ? { sourceRefs } : null
}

function parseLooseJsonObject(value: string): Record<string, unknown> | null {
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]
  const content = fenced?.trim() ?? value.trim()
  const start = content.indexOf('{')
  const end = content.lastIndexOf('}')
  if (start < 0 || end <= start) return null
  try {
    const parsed = JSON.parse(content.slice(start, end + 1)) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function isActionCountQuestion(value: string): boolean {
  return /\b(?:how many|number|count|total)\b/i.test(value) && requestedActionNames(value).length > 0
}

function isCountQuestion(value: string): boolean {
  return /\b(?:how many|number|count|total)\b/i.test(value)
}

function replaceFinalAnswer(
  result: RunAgentLoopResult,
  corrected: string,
  guard: { decisionKind: string; expected: number | string; observed: number | string | null },
): RunAgentLoopResult {
  const messages = [...result.messages]
  let replaced = false
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index]
    if (message.role === 'assistant' && !(message.tool_calls?.length)) {
      messages[index] = { ...message, content: corrected }
      replaced = true
      break
    }
  }
  if (!replaced) messages.push({ role: 'assistant', content: corrected })
  const turn = result.events.filter(event => event.type === 'model_turn_start').at(-1)?.turn ?? 0
  return {
    ...result,
    status: 'completed',
    messages,
    output: corrected,
    events: [...result.events, {
      type: 'answer_guard_applied',
      turn,
      ...guard,
    }],
  }
}

function correctedNoAnswer(report: StructuredEvidenceReport): string {
  const missing = report.missing_information
    .map(item => item.trim().replace(/[.\s]+$/, ''))
    .filter(Boolean)
    .slice(0, 2)
  return missing.length > 0
    ? `The available memory does not provide enough information to answer this question. Missing evidence: ${missing.join('; ')}.`
    : 'The available memory does not provide enough information to answer this question.'
}

function correctedEvidenceAnswer(
  decision: EvidenceDecision,
  report: StructuredEvidenceReport | null,
): string {
  if (decision.kind === 'pending_action_count') {
    const actions = report?.pending_action_ledger
      .filter(action => decision.action_ids.includes(action.id))
      .map(action => `${action.action} ${action.object}`)
      ?? []
    return actions.length > 0
      ? `There are ${decision.count} distinct pending actions: ${actions.join('; ')}.`
      : `There are ${decision.count} distinct pending actions matching the requested operations.`
  }
  if (decision.kind === 'temporal_interval_days') {
    return `The two supported events were ${decision.count} days apart.`
  }
  const events = report?.event_ledger
    .filter(event => decision.event_ids.includes(event.id))
    .map(event => event.object)
    ?? []
  if (decision.kind === 'event_entity_count') {
    return events.length > 0
      ? `There are ${decision.count} supported acquisitions: ${events.join('; ')}.`
      : `There are ${decision.count} supported acquisition events.`
  }
  return events.length > 0
    ? `There are ${decision.count} explicitly supported projects: ${events.join('; ')}.`
    : `There are ${decision.count} explicitly supported leadership events.`
}

function extractStatedCount(output: string): number | null {
  const plain = output.replace(/[*_`]/g, '')
  const match = plain.match(/(?:there\s+(?:are|were)|you\s+(?:have|had|need)|answer\s+is|total(?:\s+is|\s+of)?)\D{0,24}(\d+)/i)
  return match ? Number(match[1]) : null
}

function extractContractedCardinality(output: string): number | null {
  const match = output.replace(/[*_`]/g, '').match(/(?:^|\b)(\d+)(?:\b|\s+distinct\b)/)
  return match?.[1] ? Number(match[1]) : null
}

function defaultEvidenceObjective(questionType?: string): string {
  if (questionType === 'temporal-reasoning') {
    return 'Build a sourced timeline with exact event anchors and explicit inclusive or exclusive boundaries. Do not answer until the date chain is represented in the ledger.'
  }
  if (questionType === 'multi-session') {
    return 'Build separate entity, event, and pending-action ledgers across sessions. Deduplicate entities but never collapse distinct actions on the same entity.'
  }
  if (questionType === 'knowledge-update') {
    return 'Build an old-to-new state ledger. Identify the same entity and predicate across both sources, preserve their dates, and select the latest explicitly supported state while recording the superseded value as an exclusion.'
  }
  if (questionType === 'single-session-assistant') {
    return 'Recover the relevant content from the prior assistant turn. Preserve speaker attribution and do not reinterpret assistant-authored content as a user belief or action.'
  }
  if (questionType === 'single-session-preference') {
    return 'Extract the user preferences and constraints that are explicitly supported by the conversation, including relevant products, tools, topics, and exclusions. Do not invent a preference from generic assistant advice.'
  }
  return 'Build a sourced evidence ledger and identify conflicts, exclusions, and missing information before the parent answers.'
}

function answerPhaseInstructions(plan: EvidenceRoutePlan | null): string[] {
  if (!plan) return []
  const instructions: string[] = []
  if (plan.profiles.includes('preference_profile')) {
    instructions.push(
      'This is a personalized generation task: use the recovered user preferences, experiences, tools, and constraints to produce useful new advice or recommendations.',
      'The exact recommendation does not need to have appeared in memory. Do not refuse merely because no prior answer to the same question was found.',
      'When relevant personal evidence exists, answer with actionable suggestions and naturally mention the details that make them personalized. Do not ask the user to repeat preferences already present in the report.',
    )
  }
  if (plan.profiles.includes('assistant_recall')) {
    instructions.push('Recover the prior assistant-authored content exactly enough to answer, while preserving that it came from the assistant.')
  }
  if (plan.profiles.includes('timeline')) {
    instructions.push('For temporal answers, include every requested event and apply the requested ordering, interval, or boundary calculation.')
  }
  if (plan.profiles.includes('state_resolution')) {
    instructions.push('For state questions, state the selected value directly; mention older values only when needed to explain a genuine update or conflict.')
  }
  return instructions
}

function evidenceQueryFromMessages(messages: readonly Message[]): { query: string; referenceDate?: string } {
  const content = [...messages].reverse().find(message => message.role === 'user')?.content ?? ''
  const query = content.match(/(?:^|\n)Question:\s*([\s\S]+)$/i)?.[1]?.trim() || content
  const referenceDate = content.match(/(?:^|\n)Question date:\s*([^\n]+)/i)?.[1]?.trim()
  return { query, ...(referenceDate ? { referenceDate } : {}) }
}
