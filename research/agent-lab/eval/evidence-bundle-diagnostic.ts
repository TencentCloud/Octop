#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

import { compileEvidenceBundle } from '../src/memory/evidence-bundle.js'
import { FileMemoryStore } from '../src/memory/store.js'

type LongMemEvalItem = {
  question_id: string
  question_type: string
  question: string
  answer: unknown
  answer_session_ids: string[]
  haystack_session_ids: string[]
  haystack_dates: string[]
  haystack_sessions: Array<Array<{ role: string; content: string }>>
}

const args = parseArgs(process.argv.slice(2))
const dataPath = path.resolve(args.data ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outDir = path.resolve(args.out ?? `../work/eval-runs/evidence-bundle-${Date.now()}`)
const maxSources = positiveInt(args.maxSources, 14)
const perType = positiveInt(args.perType, 5)
const offset = nonNegativeInt(args.offset, 0)
const types = (args.types ?? 'temporal-reasoning,multi-session,knowledge-update')
  .split(',').map(value => value.trim()).filter(Boolean)
const requestedIds = new Set((args.ids ?? '').split(',').map(value => value.trim()).filter(Boolean))
const allItems = JSON.parse(await fs.readFile(dataPath, 'utf8')) as LongMemEvalItem[]
const selected = requestedIds.size > 0
  ? allItems.filter(item => requestedIds.has(item.question_id))
  : types.flatMap(type => allItems
      .filter(item => item.question_type === type && !item.question_id.includes('_abs'))
      .slice(offset, offset + perType))
const summaryTypes = requestedIds.size > 0
  ? [...new Set(selected.map(item => item.question_type))]
  : types

await fs.mkdir(outDir, { recursive: true })
const rows: Record<string, unknown>[] = []
for (let index = 0; index < selected.length; index++) {
  const item = selected[index]!
  const store = new FileMemoryStore(path.join(outDir, 'episodes', safeName(item.question_id), 'memory'))
  await ingestEpisode(store, item)
  const expectedRole = item.question_type === 'single-session-assistant' ? 'assistant' : 'user'
  const bundle = await compileEvidenceBundle(store, item.question, {
    maxSources,
    maxChars: 26_000,
    preferredRole: expectedRole,
  })
  const selectedSources = bundle.source_clusters.map(cluster => cluster.source_ref)
  const expectedSources = [...new Set(item.answer_session_ids)]
  const foundSources = expectedSources.filter(source => selectedSources.includes(source))
  const roleCoveredSources = expectedSources.filter(source => bundle.source_clusters.some(cluster =>
    cluster.source_ref === source && cluster.snippets.some(snippet => snippet.role === expectedRole),
  ))
  const row = {
    question_id: item.question_id,
    question_type: item.question_type,
    expected_sources: expectedSources,
    selected_sources: selectedSources,
    found_sources: foundSources,
    source_recall: expectedSources.length > 0 ? foundSources.length / expectedSources.length : 1,
    source_precision: selectedSources.length > 0
      ? selectedSources.filter(source => expectedSources.includes(source)).length / selectedSources.length
      : 0,
    expected_role: expectedRole,
    role_covered_sources: roleCoveredSources,
    role_coverage: expectedSources.length > 0 ? roleCoveredSources.length / expectedSources.length : 1,
    covered_facets: bundle.covered_facets,
    uncovered_facets: bundle.uncovered_facets,
    bundle_chars: bundle.stats.chars,
    bundle_truncated: bundle.stats.truncated,
  }
  rows.push(row)
  console.error(`[${index + 1}/${selected.length}] ${item.question_id} recall=${row.source_recall.toFixed(2)} sources=${selectedSources.length}`)
}

const summary = {
  data: dataPath,
  outDir,
  count: rows.length,
  maxSources,
  offset,
  meanSourceRecall: mean(rows.map(row => Number(row.source_recall))),
  perfectSourceRecallRate: mean(rows.map(row => Number(row.source_recall) === 1 ? 1 : 0)),
  meanSourcePrecision: mean(rows.map(row => Number(row.source_precision))),
  meanRoleCoverage: mean(rows.map(row => Number(row.role_coverage))),
  meanBundleChars: mean(rows.map(row => Number(row.bundle_chars))),
  byType: Object.fromEntries(summaryTypes.map(type => {
    const subset = rows.filter(row => row.question_type === type)
    return [type, {
      count: subset.length,
      meanSourceRecall: mean(subset.map(row => Number(row.source_recall))),
      perfectSourceRecallRate: mean(subset.map(row => Number(row.source_recall) === 1 ? 1 : 0)),
      meanRoleCoverage: mean(subset.map(row => Number(row.role_coverage))),
    }]
  })),
}
await fs.writeFile(path.join(outDir, 'bundle-diagnostic.jsonl'), rows.map(row => JSON.stringify(row)).join('\n') + '\n', 'utf8')
await fs.writeFile(path.join(outDir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n', 'utf8')
console.log(JSON.stringify(summary, null, 2))

async function ingestEpisode(store: FileMemoryStore, item: LongMemEvalItem): Promise<void> {
  for (let index = 0; index < item.haystack_sessions.length; index++) {
    const session = item.haystack_sessions[index]!
    const sessionId = String(item.haystack_session_ids[index] ?? `session-${index}`)
    const sessionDate = String(item.haystack_dates[index] ?? 'unknown')
    const content = session.map(turn => `${turn.role}: ${turn.content}`).join('\n')
    const userText = session.filter(turn => turn.role === 'user').map(turn => turn.content).join(' ')
    await store.create({
      kind: 'episodic',
      title: `Conversation session ${sessionId}`,
      summary: userText.slice(0, 1_200) || content.slice(0, 1_200),
      content,
      tags: ['longmemeval', item.question_type],
      source: { type: 'conversation', ref: sessionId, observed_at: normalizeDate(sessionDate) },
      temporal: { event_time: sessionDate },
      confidence: 1,
    })
  }
}

function normalizeDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? new Date(0).toISOString() : parsed.toISOString()
}

function mean(values: readonly number[]): number {
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
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

function parseArgs(argv: string[]): Record<string, string> {
  const parsed: Record<string, string> = {}
  for (let index = 0; index < argv.length; index++) {
    const token = argv[index]!
    if (!token.startsWith('--')) continue
    parsed[token.slice(2)] = argv[index + 1] && !argv[index + 1]!.startsWith('--') ? argv[++index]! : 'true'
  }
  return parsed
}
