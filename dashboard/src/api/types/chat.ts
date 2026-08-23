export interface ChatSpec {
  id: string; // Chat UUID identifier
  name?: string; // Chat name
  session_id: string; // Session identifier (channel-userid format)
  user_id: string; // User identifier
  peer_user_id?: string; // Peer user identifier for dual-user channels
  canonical_user_id?: string; // Cross-channel canonical user identifier
  channel: string; // Channel name, default: "default"
  created_at: string | null; // Chat creation timestamp (ISO 8601)
  updated_at: string | null; // Chat last update timestamp (ISO 8601)
  meta?: Record<string, unknown>; // Additional metadata
}

export interface TokenUsage {
  input_tokens?: number;
  uncached_input_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  output_tokens?: number;
  reasoning_tokens?: number;
  total_tokens?: number;
  model_calls?: number;
  last_input_tokens?: number;
  input_token_details?: Record<string, unknown>;
  output_token_details?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ProcessErrorInfo {
  message?: string;
  code?: string | number;
  source?: string;
  status_code?: number;
  retryable?: boolean;
  [key: string]: unknown;
}

export interface MessageMetadata {
  response_metadata?: Record<string, unknown>;
  additional_kwargs?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface MessageEventMetadata {
  usage?: TokenUsage;
  [key: string]: unknown;
}

export interface ResponseEventMetadata {
  run_usage?: TokenUsage;
  [key: string]: unknown;
}

export interface Message {
  role: string;
  content: unknown;
  usage?: TokenUsage;
  metadata?: MessageMetadata;
  [key: string]: unknown;
}

export interface ChatHistory {
  messages: Message[];
}

export interface CallEntry {
  entry_index?: string;
  message_id?: string | null;
  role?: string | null;
  content: unknown[];
  usage?: TokenUsage;
  metadata?: Record<string, unknown> | null;
  timestamp?: number;
  [key: string]: unknown;
}

export interface CallHistory {
  entries: CallEntry[];
}

export interface ChatDeleteResponse {
  success: boolean;
  chat_id: string;
}

// Legacy Session type alias for backward compatibility
export type Session = ChatSpec;
