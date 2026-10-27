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
  /**
   * Offloaded ``octop_ui`` payload. When the backend strips a large ``data``
   * field from the tool output (envelope carries ``data_ref: "artifact"``),
   * the full payload lands here — never in the model's context.
   */
  artifact?: unknown;
  errorCode?: string;
  returnCode?: number;
  /** Owning plugin id when known (from tool index / SSE). */
  pluginId?: string;
}

export interface HitlActionRequest {
  name: string;
  args?: Record<string, unknown>;
  description?: string;
}

export type HitlRequestResolution = "approve" | "allow_tool" | "allow_all";

export interface HitlRequestData {
  action_requests: HitlActionRequest[];
  review_configs?: Array<{ action_name: string; allowed_decisions: string[] }>;
  status?: "pending" | "approved" | "rejected";
  resolution?: HitlRequestResolution;
  pending_id?: string;
}

export interface ChatAttachment {
  url: string;
  filename?: string;
  mediaType?: string;
  workspacePath?: string;
  kind: "image" | "file" | "video" | "audio";
}

/** Skills, connectors, knowledge bases, experts, and selected model attached at send time. */
export interface UserComposerContext {
  skills?: string[];
  connectors?: string[];
  knowledgeBaseIds?: string[];
  targetAgents?: string[];
  model?: string;
  reasoningMode?: "auto" | "enabled" | "disabled";
  reasoningEffort?: string | null;
}

export interface DecisionNoticePart {
  kind: "skill" | "tool" | "member" | "result";
  /** Null when that catalog was left unchanged. An empty list means it was narrowed to nothing extra. */
  kept: Array<{ name: string; score?: number }> | null;
}

/** Notice that a decision model narrowed this reply. Stored on the assistant message. */
export interface DecisionNotice {
  model: string;
  empty: boolean;
  parts: DecisionNoticePart[];
}

export function parseDecisionNotice(data: unknown): DecisionNotice | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const raw = data as Record<string, unknown>;
  if (raw.kind !== "decision") return null;
  const partsRaw = Array.isArray(raw.parts) ? raw.parts : [];
  const parts: DecisionNoticePart[] = [];
  for (const item of partsRaw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const kind = row.kind;
    if (
      kind !== "skill" &&
      kind !== "tool" &&
      kind !== "member" &&
      kind !== "result"
    ) {
      continue;
    }
    if (row.kept == null) {
      parts.push({ kind, kept: null });
      continue;
    }
    if (!Array.isArray(row.kept)) continue;
    const kept = row.kept.flatMap((entry) => {
      if (!entry || typeof entry !== "object") return [];
      const name = (entry as { name?: unknown }).name;
      if (typeof name !== "string" || !name.trim()) return [];
      const score = (entry as { score?: unknown }).score;
      return [
        {
          name,
          ...(typeof score === "number" ? { score } : {}),
        },
      ];
    });
    parts.push({ kind, kept });
  }
  return {
    model: typeof raw.model === "string" ? raw.model : "",
    empty: raw.empty === true,
    parts,
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  type?: string;
  /** Structured content blocks for multi-part messages (thinking + text). */
  contentBlocks?: ContentBlockItem[];
  attachments?: ChatAttachment[];
  /** Optimistic mid-turn steer that can still be withdrawn. */
  steerPending?: boolean;
  composerContext?: UserComposerContext;
  toolData?: ToolCallData;
  hitlData?: HitlRequestData;
  usage?: TokenUsage;
  metadata?: MessageMetadata;
  errorInfo?: ProcessErrorInfo;
  status?: "streaming" | "done" | "error";
  timestamp: number;
  /**
   * Team room speaker. When a member is fanned into the host thread, this is
   * that member's agent id so the bubble can render as a separate person.
   */
  speakerAgentId?: string;
  /** Host wrap-up after members — never continue the dispatch bubble. */
  teamWrapup?: boolean;
  /**
   * Workspace paths written/edited in this turn. Stamped on the final
   * (or last file-tool) assistant bubble so the edit-file card still
   * shows when process tools are collapsed; full tool trail is also
   * persisted for the process panel.
   */
  editedFiles?: string[];
  /** Decision-model pass for this turn. Shown inside the process fold. */
  decision?: DecisionNotice;
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
  historyNextCursor?: string | null;
  historyLoadingMore: boolean;
  /** True after the first history fetch finished (even if empty). */
  historyHydrated: boolean;
  /** Server-side messages changed outside this client — refetch on next load. */
  historyStale: boolean;
  listeners: Set<() => void>;
  /** Cached snapshot reference (updated on every notify). */
  _snapshot: SessionSnapshot;
  /** Room / chat agent id — team host tokens are stamped with this. */
  roomAgentId?: string;
  /** Team host room — listen-only sockets and ask_agent continue stay on. */
  isTeamRoom?: boolean;
  pendingPlanPath?: string | null;
  /**
   * Speakers that still own an open generation (token / tool / reasoning)
   * until their ``done`` frame. Empty string = unlabeled host. Keeps process
   * panels open across tool gaps after the composer has unlocked.
   */
  liveSpeakers: Set<string>;
  /** Mid-turn steer: ``turn.started`` / ``turn.resumed`` id (issue #1300). */
  activeTurnId?: string | null;
  /** Server-acked undrained steers (internal; drives transcript lifecycle). */
  pendingSteers: Array<{
    clientPendingId: string;
    pendingId: string;
    preview: string;
    /** Client-only full text (frames carry 200-char previews). */
    text?: string;
    attachments?: ChatAttachment[];
    /** ``steer_remove`` is in flight; the row stays until ``steer.ack``. */
    withdrawing?: boolean;
  }>;
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
  historyNextCursor?: string | null;
  historyHydrated: boolean;
  pendingPlanPath?: string | null;
  /** Sorted speaker keys still generating (see SessionStreamState.liveSpeakers). */
  liveSpeakers: string[];
  activeTurnId?: string | null;
}
