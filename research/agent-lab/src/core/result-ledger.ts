import type { StructuredEvidenceResult } from '../memory/evidence-result.js'

export type ResultLedgerStatus = 'completed' | 'max_turns_exceeded'

export type ResultLedgerRecord = {
  id: string
  subagentId: string
  kind: string
  description: string
  objective: string
  status: ResultLedgerStatus
  summary: string
  output: string
  contextPrelude?: string
  discoveredEvidence?: string
  evidenceResult?: StructuredEvidenceResult
  evidenceResultErrors?: string[]
  evidenceFactValid?: boolean
  evidenceCoverageComplete?: boolean
  evidenceFactErrors?: string[]
  evidenceCoverageErrors?: string[]
}

export type ResultLedgerStore = {
  put(record: ResultLedgerRecord): Promise<void>
  get(id: string): Promise<ResultLedgerRecord | null>
  list(): Promise<ResultLedgerRecord[]>
}

export class InMemoryResultLedgerStore implements ResultLedgerStore {
  private readonly records = new Map<string, ResultLedgerRecord>()

  async put(record: ResultLedgerRecord): Promise<void> {
    this.records.set(record.id, structuredClone(record))
  }

  async get(id: string): Promise<ResultLedgerRecord | null> {
    const record = this.records.get(id)
    return record ? structuredClone(record) : null
  }

  async list(): Promise<ResultLedgerRecord[]> {
    return [...this.records.values()].map(record => structuredClone(record))
  }
}

export function summarizeLedgerResult(output: string, maxChars = 200): string {
  const compact = output.replace(/\s+/g, ' ').trim()
  if (compact.length <= maxChars) return compact
  return `${compact.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`
}
