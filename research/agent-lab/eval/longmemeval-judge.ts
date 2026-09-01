#!/usr/bin/env node
import { promises as fs } from 'node:fs'
import path from 'node:path'

import { createOpenAICompatibleStreamRequest } from '../src/adapters/openai-compatible-client.js'
import { createTokenHubStreamingModel } from '../src/adapters/tokenhub-stream.js'
import { runAgentLoop } from '../src/core/agent-loop.js'
import { createUserMessage } from '../src/core/messages.js'
import { createPermissionContext } from '../src/core/permissions.js'

type HypothesisRow = {
  question_id: string
  hypothesis: string
  [key: string]: unknown
}

type ReferenceRow = {
  question_id: string
  question_type: string
  question: string
  answer: unknown
}

const args = parseArgs(process.argv.slice(2))
const hypothesisPath = path.resolve(requiredArg(args, 'hypotheses'))
const referencePath = path.resolve(args.references ?? '../LongMemEval/data/longmemeval_s_cleaned.json')
const outputPath = path.resolve(args.out ?? `${hypothesisPath}.judge-glm52.jsonl`)
const concurrency = positiveInt(args.concurrency, 8)
const modelName = args.model ?? process.env.MEMORY_TREE_MODEL ?? process.env.OPENAI_MODEL ?? 'glm-5.2'
const apiKey = process.env.MEMORY_TREE_API_KEY ?? process.env.OPENAI_API_KEY ?? process.env.TOKENHUB_API_KEY ?? ''
const baseUrl = process.env.MEMORY_TREE_BASE_URL ?? process.env.OPENAI_BASE_URL ?? process.env.TOKENHUB_BASE_URL ?? ''
if (!apiKey || !baseUrl) throw new Error('TokenHub/OpenAI-compatible API configuration is missing')

const hypotheses = await loadJsonl<HypothesisRow>(hypothesisPath)
const references = JSON.parse(await fs.readFile(referencePath, 'utf8')) as ReferenceRow[]
const referencesById = new Map(references.map(row => [row.question_id, row]))
const previous = args.resume === 'true' ? await loadJsonlIfExists<HypothesisRow>(outputPath) : []
const completed = new Map(previous.map(row => [row.question_id, row]))
await fs.mkdir(path.dirname(outputPath), { recursive: true })
await fs.writeFile(outputPath, previous.length ? `${previous.map(row => JSON.stringify(row)).join('\n')}\n` : '', 'utf8')

const request = createOpenAICompatibleStreamRequest({
  apiKey,
  baseUrl,
  model: modelName,
  maxTokens: positiveInt(args.maxTokens, 2_048),
  timeoutMs: positiveInt(args.timeoutMs, 180_000),
})
const model = createTokenHubStreamingModel(request)
const permissionContext = createPermissionContext({
  cwd: process.cwd(),
  readableRoots: [process.cwd()],
  writableRoots: [],
  toolRules: {},
})
let cursor = 0
let writeQueue = Promise.resolve()

async function worker(workerId: number): Promise<void> {
  while (true) {
    const index = cursor++
    const hypothesis = hypotheses[index]
    if (!hypothesis) return
    if (completed.has(hypothesis.question_id)) continue
    const reference = referencesById.get(hypothesis.question_id)
    if (!reference) throw new Error(`Missing reference for ${hypothesis.question_id}`)
    try {
      const result = await runAgentLoop({
        model,
        tools: [],
        permissionContext,
        messages: [createUserMessage(judgePrompt(reference, hypothesis.hypothesis))],
        maxTurns: 3,
      })
      const raw = result.output?.trim() ?? ''
      const label = parseJudgeLabel(raw)
      const row = {
        ...hypothesis,
        autoeval_label: { model: modelName, label, raw },
      }
      completed.set(hypothesis.question_id, row)
      writeQueue = writeQueue.then(() => fs.appendFile(outputPath, `${JSON.stringify(row)}\n`, 'utf8'))
      await writeQueue
      console.error(`[${completed.size}/${hypotheses.length}] worker=${workerId} ${hypothesis.question_id} ${label ? 'yes' : 'no'}`)
    } catch (error) {
      console.error(`[judge-error] worker=${workerId} ${hypothesis.question_id}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
}

await Promise.all(Array.from({ length: concurrency }, (_, index) => worker(index + 1)))
await writeQueue

const judged = await loadJsonl<HypothesisRow & { autoeval_label?: { label?: boolean } }>(outputPath)
const unique = new Map(judged.map(row => [row.question_id, row]))
const finalRows = hypotheses.flatMap(row => {
  const judgedRow = unique.get(row.question_id)
  return judgedRow ? [judgedRow] : []
})
await fs.writeFile(outputPath, finalRows.length ? `${finalRows.map(row => JSON.stringify(row)).join('\n')}\n` : '', 'utf8')
const summary = summarize(finalRows, referencesById, hypotheses.length, modelName)
await fs.writeFile(`${outputPath}.summary.json`, `${JSON.stringify(summary, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(summary, null, 2))

function judgePrompt(reference: ReferenceRow, hypothesis: string): string {
  if (reference.question_id.includes('_abs')) {
    return `I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: ${reference.question}\n\nExplanation: ${String(reference.answer)}\n\nModel Response: ${hypothesis}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only.`
  }
  if (reference.question_type === 'single-session-preference') {
    return `I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: ${reference.question}\n\nRubric: ${String(reference.answer)}\n\nModel Response: ${hypothesis}\n\nIs the model response correct? Answer yes or no only.`
  }
  if (reference.question_type === 'knowledge-update') {
    return `I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: ${reference.question}\n\nCorrect Answer: ${String(reference.answer)}\n\nModel Response: ${hypothesis}\n\nIs the model response correct? Answer yes or no only.`
  }
  const temporalRule = reference.question_type === 'temporal-reasoning'
    ? ' In addition, do not penalize off-by-one errors for elapsed time. If the response is off by one day, week, month, or equivalent unit, it is still correct.'
    : ''
  return `I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps needed to get the correct answer, answer yes. If it only contains a subset of the required information, answer no.${temporalRule}\n\nQuestion: ${reference.question}\n\nCorrect Answer: ${String(reference.answer)}\n\nModel Response: ${hypothesis}\n\nIs the model response correct? Answer yes or no only.`
}

function parseJudgeLabel(raw: string): boolean {
  const labels = raw.toLowerCase().match(/\b(?:yes|no)\b/g) ?? []
  return labels.at(-1) === 'yes'
}

function summarize(
  rows: Array<HypothesisRow & { autoeval_label?: { label?: boolean } }>,
  referencesById: ReadonlyMap<string, ReferenceRow>,
  expected: number,
  model: string,
) {
  const judgedRows = rows.filter(row => typeof row.autoeval_label?.label === 'boolean')
  const correct = judgedRows.filter(row => row.autoeval_label?.label === true).length
  const types = [...new Set(judgedRows.map(row => referencesById.get(row.question_id)?.question_type).filter(Boolean))] as string[]
  return {
    model,
    expected,
    judged: judgedRows.length,
    missing: expected - judgedRows.length,
    correct,
    incorrect: judgedRows.length - correct,
    accuracy: judgedRows.length ? correct / judgedRows.length : 0,
    by_type: Object.fromEntries(types.map(type => {
      const subset = judgedRows.filter(row => referencesById.get(row.question_id)?.question_type === type)
      const typeCorrect = subset.filter(row => row.autoeval_label?.label === true).length
      return [type, { count: subset.length, correct: typeCorrect, accuracy: subset.length ? typeCorrect / subset.length : 0 }]
    })),
    abstention: (() => {
      const subset = judgedRows.filter(row => row.question_id.includes('_abs'))
      const subsetCorrect = subset.filter(row => row.autoeval_label?.label === true).length
      return { count: subset.length, correct: subsetCorrect, accuracy: subset.length ? subsetCorrect / subset.length : 0 }
    })(),
  }
}

async function loadJsonl<T>(filePath: string): Promise<T[]> {
  return (await fs.readFile(filePath, 'utf8')).split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line) as T)
}

async function loadJsonlIfExists<T>(filePath: string): Promise<T[]> {
  try {
    return await loadJsonl<T>(filePath)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

function requiredArg(args: Record<string, string>, name: string): string {
  const value = args[name]
  if (!value) throw new Error(`--${name} is required`)
  return value
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
    parsed[token.slice(2)] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : 'true'
  }
  return parsed
}
