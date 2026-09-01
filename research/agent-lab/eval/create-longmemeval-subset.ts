#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import path from 'node:path'

type DatasetItem = {
  question_id: string
  question_type: string
}

const TYPES = [
  'single-session-user',
  'single-session-assistant',
  'single-session-preference',
  'temporal-reasoning',
  'multi-session',
  'knowledge-update',
] as const

const args = parseArgs(process.argv.slice(2))
const dataPath = path.resolve(args.data ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outputPath = path.resolve(args.out ?? 'eval/subsets/longmemeval-six-types-30.json')
const perType = positiveInt(args.perType, 30)
const seed = args.seed ?? 'evidence-planner-v1'
const items = JSON.parse(await fs.readFile(dataPath, 'utf8')) as DatasetItem[]

const selected = TYPES.flatMap(questionType => {
  const candidates = items
    .filter(item => item.question_type === questionType && !item.question_id.endsWith('_abs'))
    .sort((left, right) => stableKey(seed, left.question_id).localeCompare(stableKey(seed, right.question_id)))
  if (candidates.length < perType) {
    throw new Error(`${questionType} has ${candidates.length} candidates, fewer than requested ${perType}`)
  }
  return candidates.slice(0, perType).map(item => ({
    question_id: item.question_id,
    question_type: item.question_type,
  }))
})

const manifest = {
  schema_version: '1.0',
  dataset: path.basename(dataPath),
  seed,
  per_type: perType,
  count: selected.length,
  runtime_contract: {
    question_type_passed_to_agent: false,
    abs_suffix_checked_at_runtime: false,
    gold_labels_in_memory_tags: false,
  },
  by_type: Object.fromEntries(TYPES.map(type => [type, selected.filter(item => item.question_type === type).length])),
  items: selected,
}

await fs.mkdir(path.dirname(outputPath), { recursive: true })
await fs.writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
console.log(JSON.stringify({ outputPath, count: selected.length, byType: manifest.by_type }, null, 2))

function stableKey(seedValue: string, id: string): string {
  return createHash('sha256').update(`${seedValue}:${id}`).digest('hex')
}

function positiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function parseArgs(argv: string[]): Record<string, string> {
  const parsed: Record<string, string> = {}
  for (let index = 0; index < argv.length; index++) {
    const token = argv[index]
    if (!token.startsWith('--')) continue
    parsed[token.slice(2)] = argv[index + 1] && !argv[index + 1]!.startsWith('--') ? argv[++index]! : 'true'
  }
  return parsed
}
