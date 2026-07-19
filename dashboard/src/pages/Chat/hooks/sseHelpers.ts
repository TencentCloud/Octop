/**
 * Chat message and per-session stream state types.
 *
 * Kept separate from chatStore.ts so utils (chatAttachments, messageParser)
 * can import types without a circular dependency on the store module.
 */

import type {
  MessageMetadata,
  ProcessErrorInfo,
  TokenUsage,
} from "../../../api/types";
import type { ContentBlockItem } from "../../../utils/messageParser";

export interface ToolCallData {
  name?: string;
  displayName?: string;
  callId?: string;
  arguments?: string;
  output?: string;
  errorCode?: string;
  returnCode?: number;
}

export interface HitlActionRequest {
  name: string;
  args?: Record<string, unknown>;
  description?: string;
}

export interface HitlRequestData {
  action_requests: HitlActionRequest[];
  review_configs?: Array<{ action_name: string; allowed_decisions: string[] }>;
  status?: "pending" | "approved" | "rejected";
}

export interface ChatAttachment {
  url: string;
  filename?: string;
  mediaType?: string;
  workspacePath?: string;
  kind: "image" | "file";
}

/** Skills, connectors, experts, and selected model attached at send time. */
export interface UserComposerContext {
  skills?: string[];
  connectors?: string[];
  targetAgents?: string[];
  model?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  type?: string;
  /** Structured content blocks for multi-part messages (thinking + text). */
  contentBlocks?: ContentBlockItem[];
  attachments?: ChatAttachment[];
  composerContext?: UserComposerContext;
  toolData?: ToolCallData;
  hitlData?: HitlRequestData;
  usage?: TokenUsage;
  metadata?: MessageMetadata;
  errorInfo?: ProcessErrorInfo;
  status?: "streaming" | "done" | "error";
  timestamp: number;
}

/** Per-session state held in the chat store's module-scoped Map. */
export interface SessionStreamState {
  messages: ChatMessage[];
  isStreaming: boolean;
  /** Wall-clock ms when the current user turn started waiting on the model. */
  thinkingStartedAt: number | null;
  runUsage: TokenUsage | null;
  /** Latest prompt/context token count from SSE state snapshots. */
  contextUsage: TokenUsage | null;
  abortController: AbortController | null;
  /** Running buffer for in-flight ``token`` chunks. */
  streamMsg: string;
  /** Id of the assistant bubble currently receiving streamed tokens. */
  streamId: string;
  /**
   * Tracks the currently appending block type. Reasoning chunks land
   * in a ``thinking`` block; tokens land in ``text``.
   */
  streamBlockType: "thinking" | "text" | "";
  /** Map from harness tool-call id (or ``idx-<n>`` fallback) → assistant bubble id. */
  toolCallIdIndex: Record<string, string>;
  historyHasMore: boolean;
  historyNextOffset: number;
  historyLoadingMore: boolean;
  listeners: Set<() => void>;
  /** Cached snapshot reference (updated on every notify). */
  _snapshot: SessionSnapshot;
}

/** Read-only snapshot shape exposed via ``chatStore.getSnapshot``. */
export interface SessionSnapshot {
  messages: ChatMessage[];
  isStreaming: boolean;
  thinkingStartedAt: number | null;
  runUsage: TokenUsage | null;
  contextUsage: TokenUsage | null;
  historyHasMore: boolean;
  historyLoadingMore: boolean;
  historyNextOffset: number;
}
