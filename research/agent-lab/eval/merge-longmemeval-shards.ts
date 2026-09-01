#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

type JsonRow = Record<string, any>

const args = parseArgs(process.argv.slice(2))
const inputDirs = requiredArg(args, 'inputs').split(',').map(value => path.resolve(value.trim()))
const outDir = path.resolve(requiredArg(args, 'out'))
const referencePath = path.resolve(args.references ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const expected = Number(args.expected ?? 500)

const references = JSON.parse(await fs.readFile(referencePath, 'utf8')) as Array<{ question_id: string }>
const order = new Map(references.map((row, index) => [row.question_id, index]))
const rows: JsonRow[] = []
const attempts: JsonRow[] = []

for (const inputDir of inputDirs) {
  const shardRows = await loadJsonl(path.join(inputDir, 'qa-agent-lab.jsonl'))
  for (const row of shardRows) {
    rows.push({
      ...row,
      sidechains: Array.isArray(row.sidechains) ? row.sidechains.map((sidechain: JsonRow) => ({
        ...sidechain,
        transcript_path: typeof sidechain.transcript_path === 'string'
          ? path.relative(outDir, path.resolve(inputDir, sidechain.transcript_path))
          : sidechain.transcript_path,
      })) : row.sidechains,
      source_shard: path.basename(inputDir),
    })
  }
  attempts.push(...await loadJsonl(path.join(inputDir, 'attempts.jsonl')))
}

const unique = new Map<string, JsonRow>()
for (const row of rows) {
  const id = String(row.question_id ?? '')
  if (!id) throw new Error('Encountered a row without question_id')
  if (unique.has(id)) throw new Error(`Duplicate question_id across shards: ${id}`)
  unique.set(id, row)
}
if (unique.size !== expected) throw new Error(`Expected ${expected} unique rows, found ${unique.size}`)

const merged = [...unique.values()].sort((left, right) =>
  (order.get(String(left.question_id)) ?? Number.MAX_SAFE_INTEGER) -
  (order.get(String(right.question_id)) ?? Number.MAX_SAFE_INTEGER))
const configSignatures = new Set(merged.map(row => JSON.stringify({
  routing_mode: row.experiment?.routing_mode,
  runtime_profile: row.experiment?.runtime_profile,
  fork_max_turns: row.experiment?.fork_max_turns,
  context_max_chars: row.experiment?.parent_context_max_chars,
  context_preserve_recent_chars: row.experiment?.parent_context_preserve_recent_chars,
  context_summary_max_chars: row.experiment?.parent_context_summary_max_chars,
})))
if (configSignatures.size !== 1) throw new Error(`Found ${configSignatures.size} runtime configuration variants`)

await fs.mkdir(outDir, { recursive: true })
await fs.writeFile(path.join(outDir, 'qa-agent-lab.jsonl'), toJsonl(merged), 'utf8')
await fs.writeFile(path.join(outDir, 'attempts.jsonl'), toJsonl(attempts), 'utf8')

const startedAttempts = attempts.filter(row => row.event === 'started')
const finishedAttemptIds = new Set(attempts
  .filter(row => row.event === 'finished')
  .map(row => String(row.attempt_id ?? '')))
const attemptCounts = new Map<string, number>()
for (const attempt of startedAttempts) {
  const id = String(attempt.question_id ?? '')
  attemptCounts.set(id, (attemptCounts.get(id) ?? 0) + 1)
}
const childReports = merged.flatMap(row => Array.isArray(row.result_ledger) ? row.result_ledger : [])
const durations = merged.flatMap(row => typeof row.timing?.episode_duration_ms === 'number'
  ? [row.timing.episode_duration_ms] : [])
const modelCalls = merged.flatMap(row => typeof row.model_calls?.total === 'number'
  ? [row.model_calls.total] : [])
const types = [...new Set(merged.map(row => String(row.question_type ?? 'unknown')))]
const summary = {
  expected,
  rows: merged.length,
  unique_ids: unique.size,
  completed: merged.filter(row => row.status === 'completed').length,
  errors: merged.filter(row => row.status === 'error').length,
  runtime_profile: merged[0]?.experiment?.runtime_profile ?? null,
  routing_mode: merged[0]?.experiment?.routing_mode ?? null,
  config_variants: configSignatures.size,
  observability_rows_complete: merged.filter(row => row.timing && row.model_calls && row.attempt).length,
  by_type: Object.fromEntries(types.map(type => [type, merged.filter(row => row.question_type === type).length])),
  abs_count: merged.filter(row => String(row.question_id).includes('_abs')).length,
  average_episode_seconds: average(durations) / 1_000,
  average_model_calls: average(modelCalls),
  average_parent_turns: average(merged.map(row => Number(row.turns ?? 0))),
  average_forks: average(merged.map(row => (row.tool_calls ?? []).filter((name: unknown) => name === 'ForkSubagent').length)),
  compiler_calls: merged.reduce((sum, row) => sum + (row.tool_calls ?? []).filter((name: unknown) => name === 'CompileEvidence').length, 0),
  compiler_repairs: merged.reduce((sum, row) => sum + (row.compile_results ?? []).filter((result: JsonRow) => result.compiler_repair_attempted === true).length, 0),
  child_reports: childReports.length,
  valid_child_reports: childReports.filter(row => row.evidence_result_valid === true).length,
  invalid_child_reports: childReports.filter(row => row.evidence_result_valid !== true).length,
  tool_errors: merged.reduce((sum, row) => sum + (row.tool_errors ?? []).length, 0),
  retry_episodes: [...attemptCounts.values()].filter(count => count > 1).length,
  started_attempts: startedAttempts.length,
  finished_attempts: attempts.filter(row => row.event === 'finished').length,
  interrupted_attempts: startedAttempts.filter(row => !finishedAttemptIds.has(String(row.attempt_id ?? ''))).length,
}
await fs.writeFile(path.join(outDir, 'run-summary.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(summary, null, 2))

function average(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

async function loadJsonl(filePath: string): Promise<JsonRow[]> {
  return (await fs.readFile(filePath, 'utf8')).split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line) as JsonRow)
}

function toJsonl(rows: JsonRow[]): string {
  return rows.length ? `${rows.map(row => JSON.stringify(row)).join('\n')}\n` : ''
}

function requiredArg(values: Record<string, string>, name: string): string {
  const value = values[name]
  if (!value) throw new Error(`--${name} is required`)
  return value
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
