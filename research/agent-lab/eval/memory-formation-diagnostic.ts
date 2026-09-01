#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

import { searchMemoryCatalog } from '../src/memory/memory-catalog.js'
import { formConversationSession } from '../src/memory/memory-formation.js'
import { FileMemoryStore } from '../src/memory/store.js'

type Item = {
  question_id: string
  question_type: string
  question: string
  haystack_session_ids: string[]
  haystack_dates: string[]
  haystack_sessions: Array<Array<{ role: string; content: string }>>
}

const args = parseArgs(process.argv.slice(2))
const dataPath = path.resolve(args.data ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outDir = path.resolve(args.out ?? `../work/eval-runs/memory-formation-diagnostic-${Date.now()}`)
const type = args.type ?? 'multi-session'
const offset = nonNegativeInt(args.offset, 10)
const count = positiveInt(args.count, 20)
const items = (JSON.parse(await fs.readFile(dataPath, 'utf8')) as Item[])
  .filter(item => item.question_type === type && !item.question_id.includes('_abs'))
  .slice(offset, offset + count)
await fs.mkdir(outDir, { recursive: true })

const rows: Record<string, unknown>[] = []
for (const item of items) {
  const root = path.join(outDir, 'episodes', safeName(item.question_id), 'memory')
  const store = new FileMemoryStore(root)
  let eventCount = 0
  for (let index = 0; index < item.haystack_sessions.length; index++) {
    const formed = await formConversationSession(store, {
      sessionId: String(item.haystack_session_ids[index] ?? `session-${index}`),
      sourceDate: String(item.haystack_dates[index] ?? 'unknown'),
      turns: item.haystack_sessions[index] ?? [],
      tags: ['longmemeval'],
    })
    eventCount += formed.events.length
  }

  const catalog = await searchMemoryCatalog(store, item.question, {
    maxSources: 16,
    maxEventsPerSource: 1,
    maxChars: 7_000,
  })
  // LongMemEval source labels are used only for offline measurement. They are
  // never written into memory metadata or supplied to the runtime agent.
  const answerSources = item.haystack_session_ids.filter(id => id.startsWith('answer_'))
  const selectedSources = new Set(catalog.cards.map(card => card.source_ref))
  const coveredAnswerSources = answerSources.filter(id => selectedSources.has(id))
  rows.push({
    question_id: item.question_id,
    question_type: item.question_type,
    session_count: item.haystack_sessions.length,
    event_count: eventCount,
    answer_source_count: answerSources.length,
    covered_answer_source_count: coveredAnswerSources.length,
    answer_source_recall: answerSources.length === 0 ? 1 : coveredAnswerSources.length / answerSources.length,
    selected_source_count: catalog.cards.length,
    selected_sources: [...selectedSources],
    missed_answer_sources: answerSources.filter(id => !selectedSources.has(id)),
    catalog_chars: catalog.stats.chars,
    catalog_truncated: catalog.stats.truncated,
  })
  console.error(`${item.question_id}: ${coveredAnswerSources.length}/${answerSources.length} answer sources`)
}

const recalls = rows.map(row => Number(row.answer_source_recall))
const summary = {
  data: dataPath,
  outDir,
  type,
  offset,
  count: rows.length,
  mean_answer_source_recall: recalls.length === 0
    ? 0
    : recalls.reduce((sum, recall) => sum + recall, 0) / recalls.length,
  perfect_answer_source_recall: rows.filter(row => row.answer_source_recall === 1).length,
  mean_selected_sources: rows.length === 0
    ? 0
    : rows.reduce((sum, row) => sum + Number(row.selected_source_count), 0) / rows.length,
  mean_events: rows.length === 0
    ? 0
    : rows.reduce((sum, row) => sum + Number(row.event_count), 0) / rows.length,
}
await fs.writeFile(path.join(outDir, 'formation-diagnostic.jsonl'), `${rows.map(row => JSON.stringify(row)).join('\n')}\n`, 'utf8')
await fs.writeFile(path.join(outDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(summary, null, 2))

function parseArgs(argv: string[]): Record<string, string> {
  const parsed: Record<string, string> = {}
  for (let index = 0; index < argv.length; index++) {
    const token = argv[index]
    if (!token.startsWith('--')) continue
    parsed[token.slice(2)] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : 'true'
  }
  return parsed
}

function positiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function nonNegativeInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback
}

function safeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, '_')
}
