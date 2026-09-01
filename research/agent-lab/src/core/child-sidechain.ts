import type { AgentEvent, Message } from './messages.js'

export type ChildSidechainStatus = 'running' | 'completed' | 'max_turns_exceeded' | 'failed'

export type ChildSidechainRecord = {
  id: string
  kind: string
  description: string
  objective: string
  status: ChildSidechainStatus
  allowedTools: string[]
  messages: Message[]
  events: AgentEvent[]
  output: string | null
  startedAt?: string
  completedAt?: string
  durationMs?: number
  error?: string
}

export type ChildSidechainStore = {
  put(record: ChildSidechainRecord): Promise<void>
  get(id: string): Promise<ChildSidechainRecord | null>
  list(): Promise<ChildSidechainRecord[]>
}

/**
 * Sidechains are kept outside the parent message list. The parent receives a
 * bounded result packet while the complete child transcript remains available
 * for inspection, retries, and future persistence adapters.
 */
export class InMemoryChildSidechainStore implements ChildSidechainStore {
  private readonly records = new Map<string, ChildSidechainRecord>()

  async put(record: ChildSidechainRecord): Promise<void> {
    this.records.set(record.id, cloneRecord(record))
  }

  async get(id: string): Promise<ChildSidechainRecord | null> {
    const record = this.records.get(id)
    return record ? cloneRecord(record) : null
  }

  async list(): Promise<ChildSidechainRecord[]> {
    return [...this.records.values()].map(cloneRecord)
  }
}

function cloneRecord(record: ChildSidechainRecord): ChildSidechainRecord {
  return structuredClone(record)
}
