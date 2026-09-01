export type LegacyMemoryKind = 'episodic' | 'semantic' | 'procedural' | 'working'
export type LifecycleMemoryKind = 'evidence' | 'event' | 'state' | 'topic' | 'deferred'
export type MemoryKind = LegacyMemoryKind | LifecycleMemoryKind
export type MemoryStatus = 'active' | 'superseded' | 'deleted'
export type EventStatus = 'pending' | 'completed' | 'cancelled' | 'uncertain'

export type MemorySource = {
  type: 'conversation' | 'tool' | 'document' | 'observation'
  ref: string
  observed_at: string
}

export type MemoryTemporal = {
  event_time?: string
  valid_from?: string
  valid_to?: string
}

export type MemoryRelationType =
  | 'supports'
  | 'contradicts'
  | 'updates'
  | 'derived_from'
  | 'related'

export type MemoryRelation = {
  type: MemoryRelationType
  target: string
}

export type MemoryRecord = {
  schema_version: '2.0'
  id: string
  kind: MemoryKind
  title: string
  summary: string
  content: string
  tags: string[]
  source: MemorySource
  source_refs: string[]
  temporal?: MemoryTemporal
  entities: string[]
  event_status?: EventStatus
  supersedes: string[]
  relations: MemoryRelation[]
  confidence: number
  status: MemoryStatus
  revision: number
  created_at: string
  updated_at: string
}

export type MemoryHit = {
  id: string
  kind: MemoryKind
  title: string
  summary: string
  summary_complete?: boolean
  tags: string[]
  source_ref: string
  source_refs: string[]
  event_time?: string
  valid_from?: string
  valid_to?: string
  entities: string[]
  event_status?: EventStatus
  status: MemoryStatus
  confidence: number
  score: number
}

export type MemoryAuditEntry = {
  timestamp: string
  operation: 'create' | 'update' | 'delete'
  memory_id: string
  revision: number
  source_ref: string
  changes?: string[]
}
