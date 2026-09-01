#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

import { createOpenAICompatibleStreamRequest } from '../src/adapters/openai-compatible-client.js'
import { createTokenHubStreamingModel } from '../src/adapters/tokenhub-stream.js'
import { createSystemMessage, createUserMessage } from '../src/core/messages.js'
import { PermissionBehavior } from '../src/core/permissions.js'
import { createMemoryAgent } from '../src/memory/runtime.js'
import { formConversationSession } from '../src/memory/memory-formation.js'

type LongMemEvalItem = {
  question_id: string
  question_type: string
  question: string
  answer: unknown
  question_date?: string
  haystack_session_ids: string[]
  haystack_dates: string[]
  haystack_sessions: Array<Array<{ role: string; content: string }>>
}

const args = parseArgs(process.argv.slice(2))
const dataPath = path.resolve(args.data ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outDir = path.resolve(args.out ?? `../work/eval-runs/agent-lab-smoke-${Date.now()}`)
const perType = positiveInt(args.perType, 1)
const offset = nonNegativeInt(args.offset, 0)
const shardCount = positiveInt(args.shardCount, 1)
const shardIndex = nonNegativeInt(args.shardIndex, 0)
if (shardIndex >= shardCount) throw new Error('--shardIndex must be less than --shardCount')
const types = (args.types ?? 'temporal-reasoning,multi-session,knowledge-update').split(',').map(value => value.trim())
const readerMode = parseReaderMode(args.readerMode)
const routingMode = parseRoutingMode(args.routingMode)
const runtimeProfile = parseRuntimeProfile(args.runtimeProfile)
const formationEnabled = routingMode === 'orchestrator-ledger-catalog' || args.memoryFormation === 'true'
const forceReaderTypes = new Set((args.forceReaderTypes ?? 'temporal-reasoning,multi-session')
  .split(',').map(value => value.trim()).filter(Boolean))
const curatorEnabled = args.curator === 'true'
const maxTurns = positiveInt(args.maxTurns, 6)
const readerMaxTurns = positiveInt(args.readerMaxTurns, 5)
const forkMaxTurns = positiveInt(args.forkMaxTurns, 6)
const contextMaxChars = positiveInt(args.contextMaxChars, 6_000)
const contextPreserveRecentChars = positiveInt(args.contextPreserveRecentChars, 3_500)
const contextSummaryMaxChars = positiveInt(args.contextSummaryMaxChars, 1_500)
const modelName = args.model ?? process.env.MEMORY_TREE_MODEL ?? process.env.OPENAI_MODEL ?? process.env.HARNESS_DEFAULT_MODEL ?? 'tokenhub/auto'
const apiKey = process.env.MEMORY_TREE_API_KEY ?? process.env.OPENAI_API_KEY ?? process.env.TOKENHUB_API_KEY ?? process.env.HARNESS_PROVIDER_TOKENHUB_API_KEY ?? ''
const baseUrl = process.env.MEMORY_TREE_BASE_URL ?? process.env.OPENAI_BASE_URL ?? process.env.TOKENHUB_BASE_URL ?? process.env.HARNESS_PROVIDER_TOKENHUB_BASE_URL ?? ''
if (!apiKey || !baseUrl) throw new Error('TokenHub/OpenAI-compatible API configuration is missing')

const allItems = JSON.parse(await fs.readFile(dataPath, 'utf8')) as LongMemEvalItem[]
const manifestIds = args.subset
  ? await loadSubsetIds(path.resolve(args.subset))
  : []
const requestedIds = new Set([
  ...(args.ids ?? '').split(',').map(value => value.trim()).filter(Boolean),
  ...manifestIds,
])
const runAll = args.all === 'true'
const unshardedSelection = requestedIds.size > 0
  ? allItems.filter(item => requestedIds.has(item.question_id))
  : runAll
    ? allItems
    : selectBalanced(allItems, types, perType, offset)
if (requestedIds.size > 0 && unshardedSelection.length !== requestedIds.size) {
  const found = new Set(unshardedSelection.map(item => item.question_id))
  throw new Error(`Unknown question ids: ${[...requestedIds].filter(id => !found.has(id)).join(', ')}`)
}
const selected = shardCount === 1
  ? unshardedSelection
  : unshardedSelection.filter((_, index) => index % shardCount === shardIndex)
const summaryTypes = requestedIds.size > 0 || runAll
  ? [...new Set(selected.map(item => item.question_type))]
  : types
await fs.mkdir(outDir, { recursive: true })
const hypothesisPath = path.join(outDir, 'qa-agent-lab.jsonl')
const attemptPath = path.join(outDir, 'attempts.jsonl')
const resume = args.resume === 'true'
const previousRows = resume ? await loadJsonlIfExists(hypothesisPath) : []
const previousAttempts = resume ? await loadJsonlIfExists(attemptPath) : []
const rows: Record<string, unknown>[] = previousRows.filter(row => row.status === 'completed')
await fs.writeFile(
  hypothesisPath,
  rows.length > 0 ? `${rows.map(row => JSON.stringify(row)).join('\n')}\n` : '',
  'utf8',
)
const completedIds = new Set(rows.map(row => String(row.question_id ?? '')))
const attemptCounts = new Map<string, number>()
for (const attempt of previousAttempts) {
  if (attempt.event !== 'started' || typeof attempt.question_id !== 'string') continue
  attemptCounts.set(attempt.question_id, (attemptCounts.get(attempt.question_id) ?? 0) + 1)
}

const request = createOpenAICompatibleStreamRequest({
  apiKey,
  baseUrl,
  model: modelName,
  maxTokens: positiveInt(args.maxTokens, 4_096),
  timeoutMs: positiveInt(args.timeoutMs, 180_000),
})

for (let index = 0; index < selected.length; index++) {
  const item = selected[index]
  if (completedIds.has(item.question_id)) {
    console.error(`[${index + 1}/${selected.length}] ${item.question_id} (${item.question_type}) resumed`)
    continue
  }
  console.error(`[${index + 1}/${selected.length}] ${item.question_id} (${item.question_type})`)
  const episodeStartedAtMs = Date.now()
  const episodeStartedAt = new Date(episodeStartedAtMs).toISOString()
  const episodeRoot = path.join(outDir, 'episodes', safeName(item.question_id))
  const episodeRootExisted = await pathExists(episodeRoot)
  const attemptNumber = (attemptCounts.get(item.question_id) ?? 0) + 1
  attemptCounts.set(item.question_id, attemptNumber)
  const attemptId = `${safeName(item.question_id)}-${attemptNumber}`
  const retryProvenance = {
    attempt_id: attemptId,
    attempt_number: attemptNumber,
    resumed: resume,
    prior_result_rows: previousRows.filter(row => row.question_id === item.question_id).length,
    prior_attempt_events: previousAttempts.filter(row => row.question_id === item.question_id).length,
    episode_root_existed: episodeRootExisted,
    episode_root_reset: episodeRootExisted,
  }
  await fs.appendFile(attemptPath, `${JSON.stringify({
    event: 'started',
    question_id: item.question_id,
    question_type: item.question_type,
    runtime_profile: runtimeProfile,
    started_at: episodeStartedAt,
    ...retryProvenance,
  })}\n`, 'utf8')
  let formationDurationMs = 0
  let agentDurationMs = 0
  try {
  if (episodeRootExisted) await fs.rm(episodeRoot, { recursive: true, force: true })
  const configPath = path.join(episodeRoot, 'memory-agent.config.json')
  await fs.mkdir(episodeRoot, { recursive: true })
  await fs.writeFile(configPath, JSON.stringify({
    memoryRoot: './memory',
    context: { maxItems: 3, maxChars: 4_000, minScore: 0.01 },
    compression: {
      maxChars: contextMaxChars,
      preserveRecentChars: contextPreserveRecentChars,
      summaryMaxChars: contextSummaryMaxChars,
    },
    curator: { enabled: false, maxTurns: 4, maxContextChars: 32_000 },
  }, null, 2), 'utf8')

  const agent = await createMemoryAgent(configPath)
  agent.permissionContext.toolRules.MemoryCreate = PermissionBehavior.DENY
  agent.permissionContext.toolRules.MemoryUpdate = PermissionBehavior.DENY
  agent.permissionContext.toolRules.MemoryDelete = PermissionBehavior.DENY
  const formationStartedAtMs = Date.now()
  const formationStats = await ingestEpisode(agent.store, item, formationEnabled)
  formationDurationMs = Date.now() - formationStartedAtMs

  const systemPrompt = routingMode === 'blind'
    ? [
        'You answer LongMemEval questions using only the supplied conversation memory evidence.',
        'Inspect source dates, speaker attribution, temporal boundaries, conflicts, and missing information carefully.',
        'You have read-only memory tools and an optional ForkEvidenceReader subagent. Decide from the question and available evidence whether any tool or subagent is needed.',
        'Use MemorySearch followed by MemoryRead when the injected evidence is insufficient. Use ForkEvidenceReader when evidence must be organized across sources, dates, speakers, conflicts, or requested facts.',
        'Do not create, update, or delete memory. Answer directly and concisely; if required evidence is absent, say that it is not available.',
      ].join('\n')
    : routingMode === 'orchestrator' || routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog'
      ? [
          'You are the parent orchestrator in a memory-agent loop.',
          routingMode === 'orchestrator-ledger-catalog'
            ? 'You receive the question, its date, and one bounded <memory_catalog> navigation snapshot. You cannot read raw memory directly.'
            : 'You receive only the question and its date. You do not receive raw memory and cannot read memory directly.',
          'Use TodoWrite to keep multi-step work explicit. Delegate bounded evidence tasks with ForkSubagent.',
          ...(routingMode === 'orchestrator-ledger-catalog' ? [
            'Inspect the supplied Episode Frontmatter and matching Event Ledger previews once. These cards are navigation hints, never final answer evidence.',
            'Use catalog memory IDs and source refs to create complementary Fork tasks: source discovery, within-source event coverage, and identity/time/dedup audit when relevant.',
            'Pass assigned memory IDs and source refs in context_refs. A child must read the referenced memory before including a claim.',
            'Do not delegate one source per Fork. In at most two initial Forks, cover all listed candidate sources: one child audits every listed source and its internal events; the other searches for omitted sources and audits identity, time boundaries, and duplicates.',
          ] : []),
          'ForkSubagent children may use only MemorySearch, MemoryRead, and MemoryEvidenceBundle. Pass those exact names in allowed_tools.',
          'Ask a child to preserve source dates, speaker attribution, temporal boundaries, conflicting states, exclusions, and missing information relevant to its task.',
          routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog'
            ? 'ForkSubagent returns only a result_id and a short summary; its complete report stays isolated in ResultLedger.'
            : 'ForkSubagent returns its complete report directly to you.',
          routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog'
            ? 'Collect relevant result_ids and call CompileEvidence before answering whenever evidence spans multiple results, sessions, dates, candidates, or conflicting states. If coverage is incomplete, delegate the named missing source or facet before compiling. Do not infer detailed answers from short summaries or catalog cards.'
            : 'Use the child result to decide whether a narrower follow-up delegation is needed.',
          routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog'
            ? 'After CompileEvidence succeeds, the evidence phase is complete: answer from its packet and do not open another broad Fork.'
            : '',
          'Do not ask the child to answer broader goals unrelated to its evidence task.',
          'Lead with the best-supported answer. For a current or latest-state question, use the newest supported state unless later evidence conflicts; mention age or uncertainty afterward without negating the supported value.',
          'When the user requests advice, use supported possessions, habits, and preferences to personalize a new answer. Do not abstain merely because the exact advice was not previously stored.',
          'For relative-time comparisons, anchor each expression to its source date. If the resulting intervals do not overlap, state the supported order without requiring an explicit comparison sentence.',
          'You own the final answer. Answer directly and concisely; when required evidence is absent, say that it is not available.',
        ].join('\n')
      : routingMode === 'planner'
      ? [
          'You are the answer synthesizer in a memory-agent orchestration loop.',
          'A runtime Evidence Planner delegates all raw memory reading to an isolated Evidence Reader.',
          'Use only the compact sourced report returned by the Reader. Do not search memory or request another tool.',
          'Preserve source dates and speaker attribution. Answer directly and concisely; if required evidence is absent, say so.',
        ].join('\n')
      : [
        'You answer LongMemEval questions using only the supplied memory evidence.',
        'Inspect source dates and temporal boundaries carefully. Prefer the latest supported state for updates.',
        'When an Evidence Reader is configured for the question type, use its sourced ledger and preserve user versus assistant attribution.',
        'If the injected packet is insufficient, use MemorySearch and then MemoryRead. Do not create, update, or delete memory.',
        'Answer the question directly and concisely. If evidence is genuinely absent, say that it is not available.',
      ].join('\n')
  const runOptions = routingMode === 'blind'
    ? {
        evidenceReaderMode: readerMode,
        maxToolCallsPerTurn: 1,
        evidenceReaderMaxTurns: readerMaxTurns,
        reserveFinalAnswerTurn: true,
        curateAfterRun: curatorEnabled,
      } as const
    : routingMode === 'orchestrator' || routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog'
      ? {
          parentMode: routingMode === 'orchestrator' ? 'orchestrator' : 'orchestrator-ledger',
          evidenceReaderMode: 'off',
          maxToolCallsPerTurn: 2,
          forkSubagentMaxTurns: forkMaxTurns,
          memoryCatalog: routingMode === 'orchestrator-ledger-catalog',
          structuredEvidenceResults: routingMode === 'orchestrator-ledger-catalog',
          runtimeProfile,
          reserveFinalAnswerTurn: true,
          curateAfterRun: curatorEnabled,
        } as const
      : routingMode === 'planner'
      ? {
          evidencePlanner: true,
          orchestratorOnly: true,
          evidenceReaderMode: readerMode,
          maxToolCallsPerTurn: 1,
          evidenceReaderMaxTurns: readerMaxTurns,
          finalAnswerWithoutTools: true,
          curateAfterRun: curatorEnabled,
        } as const
      : {
        forceEvidenceReader: forceReaderTypes.has(item.question_type),
        questionType: item.question_type,
        evidenceObjective: item.question_id.includes('_abs')
          ? 'Audit whether every entity, relation, time range, and comparison operand requested by the question is explicitly supported. Distinguish an explicit zero from missing information; return answerability=no_answer when any required fact is absent.'
          : undefined,
        enforceNoAnswerGuard: item.question_id.includes('_abs'),
        evidenceReaderMode: readerMode,
        maxToolCallsPerTurn: 1,
        evidenceReaderMaxTurns: readerMaxTurns,
        finalAnswerWithoutTools: true,
        curateAfterRun: curatorEnabled,
      } as const
  const agentStartedAtMs = Date.now()
  const result = await agent.run(createTokenHubStreamingModel(request), [
    createSystemMessage(systemPrompt),
    createUserMessage(`Question date: ${item.question_date ?? 'unknown'}\nQuestion: ${item.question}`),
  ], maxTurns, undefined, runOptions)
  agentDurationMs = Date.now() - agentStartedAtMs

  const contextEvents = result.events.filter(event => event.type === 'context_prepared')
  const forkResults = result.messages.flatMap(message =>
    message.role === 'tool' && message.tool_name === 'ForkEvidenceReader'
      ? [{ is_error: message.is_error, content: message.content }]
      : [],
  )
  const readerOutcomes = forkResults.flatMap(result => parseReaderOutcome(result.content))
  const sidechains = await agent.sidechains.list()
  const ledgerResults = await agent.results.list()
  const parentModelCalls = result.events.filter(event => event.type === 'model_turn_start').length
  const subagentModelCalls = result.events
    .filter(event => event.type === 'subagent_end')
    .reduce((sum, event) => sum + (event.type === 'subagent_end' ? event.childTurns : 0), 0)
  const episodeCompletedAtMs = Date.now()
  const sidechainDir = path.join(episodeRoot, 'sidechains')
  if (sidechains.length > 0) {
    await fs.mkdir(sidechainDir, { recursive: true })
    await Promise.all(sidechains.map(sidechain => fs.writeFile(
      path.join(sidechainDir, `${safeName(sidechain.id)}.json`),
      `${JSON.stringify(sidechain, null, 2)}\n`,
      'utf8',
    )))
  }
  const row = {
    question_id: item.question_id,
    question_type: item.question_type,
    hypothesis: result.output ?? '',
    reference_answer: item.answer,
    status: result.status,
    turns: parentModelCalls,
    model_calls: {
      parent: parentModelCalls,
      subagent: subagentModelCalls,
      total: parentModelCalls + subagentModelCalls,
    },
    timing: {
      started_at: episodeStartedAt,
      completed_at: new Date(episodeCompletedAtMs).toISOString(),
      episode_duration_ms: episodeCompletedAtMs - episodeStartedAtMs,
      formation_duration_ms: formationDurationMs,
      agent_duration_ms: agentDurationMs,
    },
    attempt: retryProvenance,
    tool_calls: result.events.filter(event => event.type === 'tool_call_start').map(event => event.type === 'tool_call_start' ? event.toolName : ''),
    tool_trace: result.events.flatMap(event => event.type === 'tool_call_start'
      ? [{ turn: event.turn, tool_name: event.toolName, input: event.input }]
      : []),
    compile_results: result.messages
      .filter(message => message.role === 'tool' && message.tool_name === 'CompileEvidence')
      .map(message => summarizeCompileResult(message.content)),
    reasoning_delta_count: result.events.filter(event => event.type === 'assistant_reasoning_delta').length,
    reasoning_only_retry_count: result.events.filter(event => event.type === 'model_empty_response_retry').length,
    malformed_tool_input_retry_count: result.events.filter(event => event.type === 'model_tool_input_retry').length,
    premature_answer_retry_count: result.events.filter(event => event.type === 'model_premature_answer_retry').length,
    tool_errors: result.events.flatMap(event => event.type === 'tool_error'
      ? [{ turn: event.turn, tool_name: event.toolName, error: event.error }]
      : []),
    subagent_runs: result.events.filter(event => event.type === 'subagent_end').map(event => event.type === 'subagent_end' ? {
      subagent_id: event.subagentId,
      kind: event.kind,
      status: event.status,
      child_turns: event.childTurns,
      child_tool_calls: event.childToolCalls,
    } : null),
    subagent_events: result.events
      .filter(event => ['subagent_start', 'subagent_end', 'subagent_error'].includes(event.type))
      .map(event => event),
    sidechains: sidechains.map(sidechain => ({
      id: sidechain.id,
      kind: sidechain.kind,
      status: sidechain.status,
      started_at: sidechain.startedAt ?? null,
      completed_at: sidechain.completedAt ?? null,
      duration_ms: sidechain.durationMs ?? null,
      allowed_tools: sidechain.allowedTools,
      message_count: sidechain.messages.length,
      transcript_chars: sidechain.messages.reduce((sum, message) => sum + message.content.length, 0),
      output_chars: sidechain.output?.length ?? 0,
      output: sidechain.output,
      transcript_path: path.relative(outDir, path.join(sidechainDir, `${safeName(sidechain.id)}.json`)),
    })),
    todo_writes: result.events.filter(event =>
      event.type === 'tool_call_start' && event.toolName === 'TodoWrite').length,
    result_ledger: ledgerResults.map(entry => ({
      id: entry.id,
      subagent_id: entry.subagentId,
      status: entry.status,
      summary: entry.summary,
      output_chars: entry.output.length,
      discovered_evidence_chars: entry.discoveredEvidence?.length ?? 0,
      evidence_result_valid: entry.evidenceResult ? !(entry.evidenceResultErrors?.length) : false,
      fact_packet_valid: entry.evidenceFactValid ?? null,
      coverage_complete: entry.evidenceCoverageComplete ?? null,
      fact_error_count: entry.evidenceFactErrors?.length ?? 0,
      coverage_error_count: entry.evidenceCoverageErrors?.length ?? 0,
      coverage_status: entry.evidenceResult?.coverage_status ?? null,
      coverage_stop_reason: entry.evidenceResult?.coverage?.stop_reason ?? null,
      candidate_count: entry.evidenceResult?.candidates.length ?? null,
      covered_source_count: entry.evidenceResult?.covered_source_refs.length ?? null,
      unexplored_source_count: entry.evidenceResult?.unexplored_source_refs.length ?? null,
      evidence_result_errors: entry.evidenceResultErrors ?? [],
    })),
    answer_guard_events: result.events.filter(event => event.type === 'answer_guard_applied'),
    experiment: {
      routing_mode: routingMode,
      runtime_profile: runtimeProfile,
      reader_mode: readerMode,
      curator_enabled: curatorEnabled,
      force_reader_types: routingMode === 'oracle' ? [...forceReaderTypes] : [],
      gold_labels_available_at_runtime: routingMode === 'oracle',
      planner_enabled: routingMode === 'planner',
      parent_raw_memory_tools: !['planner', 'orchestrator', 'orchestrator-ledger', 'orchestrator-ledger-catalog'].includes(routingMode),
      memory_formation_enabled: formationEnabled,
      memory_catalog_enabled: routingMode === 'orchestrator-ledger-catalog',
      formation: formationStats,
      fork_max_turns: forkMaxTurns,
      parent_context_max_chars: contextMaxChars,
      parent_context_preserve_recent_chars: contextPreserveRecentChars,
      parent_context_summary_max_chars: contextSummaryMaxChars,
      fork_result_mode: routingMode === 'orchestrator-ledger' || routingMode === 'orchestrator-ledger-catalog' ? 'ledger' : 'inline',
    },
    fork_results: forkResults,
    reader_observability: readerOutcomes.map(outcome => ({
      report_valid: outcome.report_valid ?? null,
      report_recovered: outcome.report_recovered ?? null,
      report_compiled: outcome.report_compiled ?? null,
      report_stages: outcome.report_stages ?? null,
      evidence_ids: Array.isArray(outcome.evidence_ids) ? outcome.evidence_ids.length : 0,
      bundle: outcome.evidence_bundle ?? null,
      trace: outcome.trace ?? null,
      reader_contract: outcome.reader_contract ?? null,
    })),
    context: contextEvents.at(-1)?.type === 'context_prepared' ? contextEvents.at(-1)?.metadata : null,
  }
  rows.push(row)
  await fs.appendFile(hypothesisPath, `${JSON.stringify(row)}\n`, 'utf8')
  await fs.appendFile(attemptPath, `${JSON.stringify({
    event: 'finished',
    question_id: item.question_id,
    status: result.status,
    completed_at: new Date(episodeCompletedAtMs).toISOString(),
    duration_ms: episodeCompletedAtMs - episodeStartedAtMs,
    ...retryProvenance,
  })}\n`, 'utf8')
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const episodeCompletedAtMs = Date.now()
    const row = {
      question_id: item.question_id,
      question_type: item.question_type,
      hypothesis: '',
      reference_answer: item.answer,
      status: 'error',
      error: message,
      timing: {
        started_at: episodeStartedAt,
        completed_at: new Date(episodeCompletedAtMs).toISOString(),
        episode_duration_ms: episodeCompletedAtMs - episodeStartedAtMs,
        formation_duration_ms: formationDurationMs,
        agent_duration_ms: agentDurationMs,
      },
      attempt: retryProvenance,
    }
    rows.push(row)
    await fs.appendFile(hypothesisPath, `${JSON.stringify(row)}\n`, 'utf8')
    await fs.appendFile(attemptPath, `${JSON.stringify({
      event: 'finished',
      question_id: item.question_id,
      status: 'error',
      error: message,
      completed_at: new Date(episodeCompletedAtMs).toISOString(),
      duration_ms: episodeCompletedAtMs - episodeStartedAtMs,
      ...retryProvenance,
    })}\n`, 'utf8')
    console.error(`[${index + 1}/${selected.length}] ${item.question_id} error: ${message}`)
  }
}

function summarizeCompileResult(content: string): Record<string, unknown> {
  try {
    const envelope = JSON.parse(content) as Record<string, unknown>
    const packet = envelope.evidence_packet && typeof envelope.evidence_packet === 'object' && !Array.isArray(envelope.evidence_packet)
      ? envelope.evidence_packet as Record<string, unknown>
      : typeof envelope.evidence_packet === 'string' ? parseLooseJsonObject(envelope.evidence_packet) : null
    return {
      status: envelope.status ?? null,
      result_ids: envelope.result_ids ?? [],
      obligation_audit_count: envelope.obligation_audit_count ?? 0,
      leadership_audit_count: envelope.leadership_audit_count ?? 0,
      discovered_coverage_audit_count: envelope.discovered_coverage_audit_count ?? 0,
      state_transition_audit_count: envelope.state_transition_audit_count ?? 0,
      cross_source_coverage: envelope.cross_source_coverage ?? null,
      compiler_repair_attempted: envelope.compiler_repair_attempted === true,
      compiler_repair_status: envelope.compiler_repair_status ?? null,
      derived_count: packet?.derived_count ?? null,
      included_count: typeof packet?.included_count === 'number'
        ? packet.included_count
        : Array.isArray(packet?.included) ? packet.included.length : 0,
      count_contract: packet?.count_contract ?? null,
      discourse_answer: packet?.discourse_answer ?? null,
      answer_contract: packet?.answer_contract ?? null,
      coverage_status: packet?.coverage_status ?? null,
      coverage_decision: packet?.coverage_decision ?? null,
      reconciliation: packet?.reconciliation ?? null,
    }
  } catch {
    return { parse_error: true }
  }
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

const summary = {
  data: dataPath,
  outDir,
  hypothesisPath,
  model: modelName,
  routingMode,
  runtimeProfile,
  readerMode,
  formationEnabled,
  forceReaderTypes: routingMode === 'oracle' ? [...forceReaderTypes] : [],
  goldLabelsAvailableAtRuntime: routingMode === 'oracle',
  curatorEnabled,
  maxTurns,
  readerMaxTurns,
  forkMaxTurns,
  contextMaxChars,
  contextPreserveRecentChars,
  contextSummaryMaxChars,
  all: runAll,
  shardCount,
  shardIndex,
  offset,
  count: rows.length,
  completed: rows.filter(row => row.status === 'completed').length,
  incomplete: rows.filter(row => row.status !== 'completed' && row.status !== 'error').length,
  errors: rows.filter(row => row.status === 'error').length,
  byType: Object.fromEntries(summaryTypes.map(type => [type, rows.filter(row => row.question_type === type).length])),
}
await fs.writeFile(path.join(outDir, 'run-summary.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(summary, null, 2))

async function loadJsonlIfExists(filePath: string): Promise<Record<string, unknown>[]> {
  try {
    const raw = await fs.readFile(filePath, 'utf8')
    return raw.split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line) as Record<string, unknown>)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath)
    return true
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false
    throw error
  }
}

async function loadSubsetIds(filePath: string): Promise<string[]> {
  const parsed = JSON.parse(await fs.readFile(filePath, 'utf8')) as {
    items?: Array<{ question_id?: unknown }>
  }
  const ids = (parsed.items ?? []).flatMap(item =>
    typeof item.question_id === 'string' ? [item.question_id] : [],
  )
  if (ids.length === 0) throw new Error(`Subset manifest has no question IDs: ${filePath}`)
  if (new Set(ids).size !== ids.length) throw new Error(`Subset manifest contains duplicate question IDs: ${filePath}`)
  return ids
}

async function ingestEpisode(
  store: Awaited<ReturnType<typeof createMemoryAgent>>['store'],
  item: LongMemEvalItem,
  formationEnabled: boolean,
) {
  let rawRecords = 0
  let frontmatterRecords = 0
  let eventRecords = 0
  for (let index = 0; index < item.haystack_sessions.length; index++) {
    const session = item.haystack_sessions[index]
    const sessionId = String(item.haystack_session_ids[index] ?? `session-${index}`)
    const sessionDate = String(item.haystack_dates[index] ?? 'unknown')
    if (formationEnabled) {
      const formed = await formConversationSession(store, {
        sessionId,
        sourceDate: sessionDate,
        turns: session,
        tags: ['longmemeval'],
      })
      rawRecords++
      frontmatterRecords++
      eventRecords += formed.events.length
      continue
    }
    const content = session.map(turn => `${turn.role}: ${turn.content}`).join('\n')
    const userText = session.filter(turn => turn.role === 'user').map(turn => turn.content).join(' ')
    await store.create({
      kind: 'episodic',
      title: `Conversation session ${sessionId}`,
      summary: userText.slice(0, 1_200) || content.slice(0, 1_200),
      content,
      tags: routingMode === 'oracle' ? ['longmemeval', item.question_type] : ['longmemeval'],
      source: { type: 'conversation', ref: sessionId, observed_at: normalizeDate(sessionDate) },
      temporal: { event_time: sessionDate },
      confidence: 1,
    })
    rawRecords++
  }
  return { raw_records: rawRecords, frontmatter_records: frontmatterRecords, event_records: eventRecords }
}

function selectBalanced(items: LongMemEvalItem[], types: string[], perType: number, offset: number): LongMemEvalItem[] {
  return types.flatMap(type => items
    .filter(item => item.question_type === type && !item.question_id.includes('_abs'))
    .slice(offset, offset + perType))
}

function normalizeDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? new Date(0).toISOString() : parsed.toISOString()
}

function safeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, '_')
}

function positiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function nonNegativeInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback
}

function parseReaderOutcome(content: string): Record<string, any>[] {
  try {
    const parsed = JSON.parse(content) as Record<string, any>
    return parsed && typeof parsed === 'object' ? [parsed] : []
  } catch {
    return []
  }
}

function parseReaderMode(value: string | undefined): 'bundle' | 'legacy' | 'off' {
  const mode = value ?? 'bundle'
  if (mode === 'bundle' || mode === 'legacy' || mode === 'off') return mode
  throw new Error('--readerMode must be bundle, legacy, or off')
}

function parseRoutingMode(value: string | undefined): 'blind' | 'orchestrator' | 'orchestrator-ledger' | 'orchestrator-ledger-catalog' | 'planner' | 'oracle' {
  const mode = value ?? 'blind'
  if (mode === 'blind' || mode === 'orchestrator' || mode === 'orchestrator-ledger' || mode === 'orchestrator-ledger-catalog' || mode === 'planner' || mode === 'oracle') return mode
  throw new Error('--routingMode must be blind, orchestrator, orchestrator-ledger, orchestrator-ledger-catalog, planner, or oracle')
}

function parseRuntimeProfile(value: string | undefined): 'current' | 'v51' {
  const profile = value ?? 'current'
  if (profile === 'current' || profile === 'v51') return profile
  throw new Error('--runtimeProfile must be current or v51')
}

function parseArgs(argv: string[]): Record<string, string> {
  const parsed: Record<string, string> = {}
  for (let index = 0; index < argv.length; index++) {
    const token = argv[index]
    if (!token.startsWith('--')) continue
    parsed[token.slice(2)] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : 'true'
  }
  return parsed
}
