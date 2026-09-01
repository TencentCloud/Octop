#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

type SidechainSummary = {
  status?: string
  transcript_chars?: number
  output_chars?: number
}

type EvalRow = {
  question_id: string
  question_type: string
  hypothesis?: string
  reference_answer?: unknown
  status?: string
  turns?: number
  tool_calls?: string[]
  todo_writes?: number
  sidechains?: SidechainSummary[]
  subagent_runs?: Array<{ child_turns?: number; child_tool_calls?: string[] }>
  tool_trace?: Array<{ tool_name?: string; input?: Record<string, unknown> }>
  autoeval_label?: { label?: boolean }
}

type ReferenceRow = {
  question_id: string
  question: string
}

const args = parseArgs(process.argv.slice(2))
const hypothesesPath = path.resolve(requiredArg(args, 'hypotheses'))
const judgePath = path.resolve(requiredArg(args, 'judge'))
const referencePath = path.resolve(args.references ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outputPath = path.resolve(args.out ?? `${judgePath}.analysis.json`)
const hypotheses = await loadJsonl<EvalRow>(hypothesesPath)
const judged = await loadJsonl<EvalRow>(judgePath)
const judgeById = new Map(judged.map(row => [row.question_id, row.autoeval_label?.label]))
const references = JSON.parse(await fs.readFile(referencePath, 'utf8')) as ReferenceRow[]
const referenceById = new Map(references.map(row => [row.question_id, row]))
const rows = hypotheses.map(row => ({ ...row, autoeval_label: { label: judgeById.get(row.question_id) } }))
const types = [...new Set(rows.map(row => row.question_type))]

const analysis = {
  hypotheses: hypothesesPath,
  judge: judgePath,
  overall: summarize(rows),
  by_type: Object.fromEntries(types.map(type => [type, summarize(rows.filter(row => row.question_type === type))])),
  by_type_conditional: Object.fromEntries(types.map(type => {
    const subset = rows.filter(row => row.question_type === type)
    return [type, conditionalSummary(subset)]
  })),
  conditional: {
    fork_used: summarize(rows.filter(row => hasFork(row))),
    fork_not_used: summarize(rows.filter(row => !hasFork(row))),
    todo_used: summarize(rows.filter(row => (row.todo_writes ?? 0) > 0)),
    todo_not_used: summarize(rows.filter(row => (row.todo_writes ?? 0) === 0)),
    one_sidechain: summarize(rows.filter(row => (row.sidechains?.length ?? 0) === 1)),
    multiple_sidechains: summarize(rows.filter(row => (row.sidechains?.length ?? 0) > 1)),
    child_max_turns: summarize(rows.filter(row =>
      row.sidechains?.some(sidechain => sidechain.status === 'max_turns_exceeded')),
    ),
  },
  failures: rows
    .filter(row => row.autoeval_label?.label === false)
    .map(row => ({
      question_id: row.question_id,
      question_type: row.question_type,
      question: referenceById.get(row.question_id)?.question ?? '',
      hypothesis: row.hypothesis ?? '',
      reference_answer: row.reference_answer,
      parent_turns: row.turns ?? 0,
      tool_calls: row.tool_calls ?? [],
      todo_writes: row.todo_writes ?? 0,
      sidechain_statuses: (row.sidechains ?? []).map(sidechain => sidechain.status),
      sidechain_count: row.sidechains?.length ?? 0,
      signals: failureSignals(row),
      fork_tasks: (row.tool_trace ?? []).flatMap(trace => {
        if (trace.tool_name !== 'ForkSubagent') return []
        return [{
          description: String(trace.input?.description ?? ''),
          prompt: String(trace.input?.prompt ?? ''),
          allowed_tools: trace.input?.allowed_tools ?? [],
        }]
      }),
    })),
}

await fs.mkdir(path.dirname(outputPath), { recursive: true })
await fs.writeFile(outputPath, `${JSON.stringify(analysis, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(analysis, null, 2))

function summarize(rows: EvalRow[]) {
  const judged = rows.filter(row => typeof row.autoeval_label?.label === 'boolean')
  const correct = judged.filter(row => row.autoeval_label?.label === true).length
  const chains = rows.flatMap(row => row.sidechains ?? [])
  const childRuns = rows.flatMap(row => row.subagent_runs ?? [])
  const transcriptChars = sum(chains.map(chain => chain.transcript_chars ?? 0))
  const outputChars = sum(chains.map(chain => chain.output_chars ?? 0))
  return {
    count: rows.length,
    judged: judged.length,
    correct,
    sr: ratio(correct, judged.length),
    errors: rows.filter(row => row.status === 'error').length,
    fork_episodes: rows.filter(hasFork).length,
    fork_rate: ratio(rows.filter(hasFork).length, rows.length),
    todo_episodes: rows.filter(row => (row.todo_writes ?? 0) > 0).length,
    todo_rate: ratio(rows.filter(row => (row.todo_writes ?? 0) > 0).length, rows.length),
    sidechains: chains.length,
    avg_sidechains: ratio(chains.length, rows.length),
    multi_sidechain_episodes: rows.filter(row => (row.sidechains?.length ?? 0) > 1).length,
    max_turn_sidechains: chains.filter(chain => chain.status === 'max_turns_exceeded').length,
    avg_parent_turns: average(rows.map(row => row.turns ?? 0)),
    avg_child_turns: average(childRuns.map(run => run.child_turns ?? 0)),
    avg_child_tool_calls: average(childRuns.map(run => run.child_tool_calls?.length ?? 0)),
    avg_sidechain_transcript_chars: average(chains.map(chain => chain.transcript_chars ?? 0)),
    avg_sidechain_output_chars: average(chains.map(chain => chain.output_chars ?? 0)),
    sidechain_compression_ratio: ratio(transcriptChars, outputChars),
  }
}

function hasFork(row: EvalRow): boolean {
  return (row.tool_calls ?? []).includes('ForkSubagent')
}

function conditionalSummary(rows: EvalRow[]) {
  return {
    todo_used: summarize(rows.filter(row => (row.todo_writes ?? 0) > 0)),
    todo_not_used: summarize(rows.filter(row => (row.todo_writes ?? 0) === 0)),
    one_sidechain: summarize(rows.filter(row => (row.sidechains?.length ?? 0) === 1)),
    multiple_sidechains: summarize(rows.filter(row => (row.sidechains?.length ?? 0) > 1)),
    child_max_turns: summarize(rows.filter(row =>
      row.sidechains?.some(sidechain => sidechain.status === 'max_turns_exceeded')),
    ),
    child_not_maxed: summarize(rows.filter(row =>
      !row.sidechains?.some(sidechain => sidechain.status === 'max_turns_exceeded')),
    ),
  }
}

function failureSignals(row: EvalRow): string[] {
  const signals: string[] = []
  if (!hasFork(row)) signals.push('no_fork')
  if ((row.sidechains?.length ?? 0) > 1) signals.push('repeated_delegation')
  if (row.sidechains?.some(sidechain => sidechain.status === 'max_turns_exceeded')) {
    signals.push('child_max_turns')
  }
  if ((row.todo_writes ?? 0) > 0) signals.push('todo_used')
  const answer = row.hypothesis ?? ''
  if (/not available|unable to|wasn't able|cannot determine|can't determine|insufficient evidence/i.test(answer)) {
    signals.push('abstained_or_missing_evidence')
  }
  if (/approximately|at least|uncertain|could be|range/i.test(answer)) signals.push('hedged_answer')
  return signals
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

function average(values: number[]): number {
  return ratio(sum(values), values.length)
}

function ratio(numerator: number, denominator: number): number {
  return denominator > 0 ? numerator / denominator : 0
}

async function loadJsonl<T>(filePath: string): Promise<T[]> {
  return (await fs.readFile(filePath, 'utf8'))
    .split(/\r?\n/)
    .filter(Boolean)
    .map(line => JSON.parse(line) as T)
}

function requiredArg(args: Record<string, string>, name: string): string {
  const value = args[name]
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
