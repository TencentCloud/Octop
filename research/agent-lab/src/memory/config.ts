import { readFile } from 'node:fs/promises'
import path from 'node:path'

export type MemoryAgentConfig = {
  memoryRoot: string
  context: {
    maxItems: number
    maxChars: number
    minScore: number
  }
  compression: {
    maxChars: number
    preserveRecentChars: number
    summaryMaxChars: number
  }
  curator: {
    enabled: boolean
    maxTurns: number
    maxContextChars: number
  }
}

const DEFAULT_CONTEXT = {
  maxItems: 6,
  maxChars: 8_000,
  minScore: 0.05,
}

const DEFAULT_COMPRESSION = {
  maxChars: 80_000,
  preserveRecentChars: 24_000,
  summaryMaxChars: 12_000,
}

const DEFAULT_CURATOR = {
  enabled: false,
  maxTurns: 5,
  maxContextChars: 40_000,
}

export async function loadMemoryAgentConfig(configPath: string): Promise<MemoryAgentConfig> {
  const absoluteConfigPath = path.resolve(configPath)
  const raw = JSON.parse(await readFile(absoluteConfigPath, 'utf8')) as Partial<MemoryAgentConfig>
  if (!raw.memoryRoot || typeof raw.memoryRoot !== 'string') {
    throw new Error('memory-agent config requires memoryRoot')
  }

  return {
    memoryRoot: path.resolve(path.dirname(absoluteConfigPath), raw.memoryRoot),
    context: {
      maxItems: positiveInteger(raw.context?.maxItems, DEFAULT_CONTEXT.maxItems),
      maxChars: positiveInteger(raw.context?.maxChars, DEFAULT_CONTEXT.maxChars),
      minScore: boundedNumber(raw.context?.minScore, DEFAULT_CONTEXT.minScore, 0, 1),
    },
    compression: {
      maxChars: positiveInteger(raw.compression?.maxChars, DEFAULT_COMPRESSION.maxChars),
      preserveRecentChars: positiveInteger(raw.compression?.preserveRecentChars, DEFAULT_COMPRESSION.preserveRecentChars),
      summaryMaxChars: positiveInteger(raw.compression?.summaryMaxChars, DEFAULT_COMPRESSION.summaryMaxChars),
    },
    curator: {
      enabled: typeof raw.curator?.enabled === 'boolean' ? raw.curator.enabled : DEFAULT_CURATOR.enabled,
      maxTurns: positiveInteger(raw.curator?.maxTurns, DEFAULT_CURATOR.maxTurns),
      maxContextChars: positiveInteger(raw.curator?.maxContextChars, DEFAULT_CURATOR.maxContextChars),
    },
  }
}

function positiveInteger(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : fallback
}

function boundedNumber(value: unknown, fallback: number, min: number, max: number): number {
  return typeof value === 'number' && value >= min && value <= max ? value : fallback
}
