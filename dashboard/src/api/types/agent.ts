export type ProcessProtocolVersion = "v1" | "v2" | "v3";

export interface AgentRequest {
  input: unknown;
  session_id?: string | null;
  user_id?: string | null;
  channel?: string | null;
  [key: string]: unknown;
}

export interface TurnInput {
  role?: string;
  content: unknown;
  metadata?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface TurnRequest {
  turn_id?: string | null;
  inputs: TurnInput[];
  stream?: boolean;
  session_id?: string | null;
  user_id?: string | null;
  peer_user_id?: string | null;
  canonical_user_id?: string | null;
  channel?: string | null;
  model?: string | null;
  top_p?: number | null;
  temperature?: number | null;
  max_tokens?: number | null;
  tools?: unknown;
  context?: Record<string, unknown> | null;
  delivery?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface TurnEvent {
  type: string;
  turn_id: string;
  sequence_number?: number | null;
  message_id?: string | null;
  role?: string | null;
  delta?: unknown;
  content?: unknown[];
  data?: unknown;
  usage?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  error?: Record<string, unknown> | string | null;
  [key: string]: unknown;
}

export interface AgentsRunningConfig {
  max_iters: number;
  max_input_length: number;
}

export interface HeartbeatConfig {
  enabled: boolean;
  every: string;
  target: string;
  active_hours_enabled: boolean;
  active_hours_start: string;
  active_hours_end: string;
}

export interface ProactiveConfig {
  enabled: boolean;
  every: string;
  target: string;
  // Backend serializes with by_alias=True → camelCase field names
  cooldown_hours?: number;
  cooldownHours?: number;
  active_hours?: { start?: string; end?: string } | null;
  activeHours?: { start?: string; end?: string } | null;
  quiet_hours?: { start?: string; end?: string } | null;
  quietHours?: { start?: string; end?: string } | null;
  daily_analysis_time?: string;
  dailyAnalysisTime?: string;
}

/** Proactive-care push config for the /api/agents/{id}/proactive-care endpoint. */
export interface ProactiveCareConfig {
  enabled: boolean;
  /** Active-window start in HH:MM format, such as "09:00". */
  active_hours_start: string;
  /** Active-window end in HH:MM format, such as "22:00". */
  active_hours_end: string;
  /** Minimum interval between pushes, in integer hours, >= 1. */
  min_interval_hours: number;
  /** Maximum interval between pushes, in integer hours, >= min_interval_hours. */
  max_interval_hours: number;
  model_ref?: string | null;
  /** Effective model when the care model follows the agent. Returned by GET. */
  readonly default_model_ref?: string | null;
  reasoning_effort?: string;
  generation_timeout_seconds?: number;
  /**
   * Episode filter.
   * null or omitted = all episodes.
   * { emotions: string[] } = filter by emotion ("positive" | "neutral" | "negative").
   */
  episode_filter?: { emotions: string[] } | null;
}
