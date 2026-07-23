import { useState, useCallback, useRef, useSyncExternalStore } from "react";
import type {
  MessageMetadata,
  TokenUsage,
  CallEntry,
} from "../../../api/types";
import * as chatStore from "./chatStore";
import {
  generateId,
  extractToolData,
  extractContentBlocks,
  extractText,
  mergeAttachments,
  type ContentBlock,
} from "../../../utils/messageParser";
import { normalizeComposerContext } from "../utils/chatMessages";
import { resolveMessageTimestampMs } from "../../../utils/formatMessageTime";
import { isImageAttachment } from "../utils/chatAttachments";
import { agentAttachmentAccessUrl } from "../../../utils/toolMediaBlocks";
import type {
  ChatAttachment,
  ChatMessage,
  UserComposerContext,
} from "./sseHelpers";

export type {
  ToolCallData,
  HitlActionRequest,
  HitlRequestData,
  ChatAttachment,
  UserComposerContext,
  ChatMessage,
} from "./sseHelpers";

export type { ContentBlockItem } from "../../../utils/messageParser";
export {
  extractContentBlocks,
  extractText,
} from "../../../utils/messageParser";

interface InternalChatMessage extends ChatMessage {
  _toolKind?: "call" | "result";
}

function normalizeTokenUsage(value: unknown): TokenUsage | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  return { ...(value as TokenUsage) };
}

function normalizeMessageMetadata(value: unknown): MessageMetadata | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  return { ...(value as MessageMetadata) };
}

/**
 * Strip Markdown image references from text when the same images are
 * already available as structured attachments.  This prevents the
 * Markdown renderer from showing a duplicate (and potentially broken
 * on page reload) image alongside the ImageGallery preview.
 */
export function stripInlineImageMarkdown(
  text: string,
  attachments: ChatAttachment[],
): string {
  if (!text || attachments.length === 0) return text;

  const attachmentUrls = new Set(attachments.map((a) => a.url));
  const attachmentFilenames = new Set(
    attachments.map((a) => a.filename).filter(Boolean) as string[],
  );

  let cleaned = text.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    (match, alt: string, url: string) => {
      const trimmedUrl = url.trim();
      if (attachmentUrls.has(trimmedUrl)) return "";
      if (alt && attachmentFilenames.has(alt)) return "";
      // Workspace/file URLs are always served via attachments
      if (
        trimmedUrl.startsWith("/api/workspace/") ||
        (trimmedUrl.startsWith("/api/agents/") &&
          (trimmedUrl.includes("/media/preview") ||
            trimmedUrl.includes("/workspace/download")))
      ) {
        return "";
      }
      return match;
    },
  );
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n").trim();
  return cleaned;
}

export function extractAttachments(content: unknown): ChatAttachment[] {
  if (!Array.isArray(content)) return [];
  return (content as ContentBlock[])
    .map((c) => {
      const anyBlock = c as Record<string, unknown>;
      const type = String(c.type || "");
      const filename =
        (anyBlock.filename as string | undefined) ||
        (anyBlock.name as string | undefined) ||
        "";
      const workspacePath =
        (anyBlock.workspace_path as string | undefined) ||
        (anyBlock.workspacePath as string | undefined);

      if (type === "image_url") {
        const imageUrlField = anyBlock.image_url;
        const url =
          typeof imageUrlField === "string"
            ? imageUrlField
            : typeof imageUrlField === "object" && imageUrlField !== null
            ? String((imageUrlField as { url?: string }).url || "")
            : "";
        if (!url && !workspacePath) return null;
        const mediaType =
          (anyBlock.media_type as string | undefined) ||
          (url.startsWith("data:") ? url.slice(5).split(";")[0] : undefined);
        return {
          url: url || "",
          filename: filename || "image",
          mediaType,
          workspacePath,
          kind: "image",
        };
      }

      if (type !== "image" && type !== "file") return null;

      const previewUrl = anyBlock.preview_url as string | undefined;
      const source = anyBlock.source as
        | string
        | { type?: string; url?: string; media_type?: string; data?: string }
        | undefined;
      const sourceUrl =
        typeof source === "string"
          ? source
          : source?.type === "url"
          ? source.url
          : undefined;
      const mediaType =
        (typeof source === "string" ? undefined : source?.media_type) ||
        (anyBlock.media_type as string | undefined);

      if (
        source &&
        typeof source !== "string" &&
        source.type === "base64" &&
        source.data
      ) {
        return {
          url: `data:${
            source.media_type || "application/octet-stream"
          };base64,${source.data}`,
          filename,
          mediaType: source.media_type,
          workspacePath,
          kind: isImageAttachment({
            kind: type === "image" ? "image" : "file",
            filename,
            mediaType,
          })
            ? "image"
            : "file",
        };
      }

      const finalUrl =
        previewUrl ||
        (typeof anyBlock.image_url === "string"
          ? (anyBlock.image_url as string)
          : undefined) ||
        (anyBlock.file_url as string | undefined) ||
        (anyBlock.url as string | undefined) ||
        sourceUrl;
      if (!finalUrl && !workspacePath) return null;

      return {
        url: finalUrl || "",
        filename,
        mediaType,
        workspacePath,
        kind: isImageAttachment({
          kind: type === "image" ? "image" : "file",
          filename,
          mediaType,
        })
          ? "image"
          : "file",
      };
    })
    .filter(Boolean) as ChatAttachment[];
}

function attachmentsFromInboundMeta(
  metadata: Record<string, unknown> | null | undefined,
): ChatAttachment[] {
  const raw = metadata?.inbound_attachments;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const workspacePath = String(
        row.workspace_path || row.workspacePath || "",
      ).trim();
      const filename = String(row.filename || "attachment");
      const mediaType = String(row.media_type || row.mediaType || "");
      const kindRaw = String(row.kind || "");
      const kind: ChatAttachment["kind"] =
        kindRaw === "image" || mediaType.startsWith("image/")
          ? "image"
          : "file";
      if (!workspacePath) return null;
      return {
        url: "",
        filename,
        mediaType: mediaType || undefined,
        workspacePath,
        kind,
      } satisfies ChatAttachment;
    })
    .filter(Boolean) as ChatAttachment[];
}

function resolveEntryTimestamp(entry: CallEntry): number {
  return resolveMessageTimestampMs(entry.timestamp);
}

function enrichAttachmentPreviewUrls(
  messages: ChatMessage[],
  agentId: string,
): ChatMessage[] {
  return messages.map((message) => {
    if (!message.attachments?.length) return message;
    const attachments = message.attachments.map((attachment) => {
      if (attachment.url || !attachment.workspacePath) return attachment;
      return {
        ...attachment,
        url: agentAttachmentAccessUrl(
          agentId,
          attachment.workspacePath,
          attachment.mediaType,
        ),
      };
    });
    return { ...message, attachments };
  });
}

function convertCallEntries(entries: CallEntry[]): ChatMessage[] {
  const raw: InternalChatMessage[] = entries.map((entry, index) => {
    const tool = extractToolData(entry.content);
    const fromMeta =
      entry.role === "user"
        ? attachmentsFromInboundMeta(
            entry.metadata as Record<string, unknown> | null | undefined,
          )
        : [];
    const attachments =
      mergeAttachments(
        fromMeta.length > 0 ? fromMeta : undefined,
        extractAttachments(entry.content),
      ) ?? undefined;
    const contentBlocks = extractContentBlocks(entry.content);
    const textContent =
      contentBlocks
        ?.filter((block) => block.type === "text")
        .map((block) => block.content)
        .join("") || extractText(entry.content);

    // Strip Markdown image references from text when the same images
    // are already available as structured attachments.
    const cleanedText =
      attachments && attachments.length > 0
        ? stripInlineImageMarkdown(textContent, attachments)
        : textContent;

    return {
      id: entry.message_id || entry.entry_index || `call-${index}`,
      role:
        entry.role === "user"
          ? "user"
          : entry.role === "tool"
          ? "tool"
          : entry.role === "system"
          ? "system"
          : "assistant",
      content: cleanedText,
      contentBlocks:
        cleanedText !== textContent && contentBlocks
          ? contentBlocks.map((b) =>
              b.type === "text"
                ? {
                    ...b,
                    content: stripInlineImageMarkdown(
                      b.content,
                      attachments ?? [],
                    ),
                  }
                : b,
            )
          : contentBlocks,
      attachments:
        attachments && attachments.length > 0 ? attachments : undefined,
      composerContext:
        entry.role === "user"
          ? normalizeComposerContext(
              (entry.metadata as Record<string, unknown> | null | undefined)
                ?.composer_context,
            )
          : undefined,
      toolData: tool?.data,
      usage: normalizeTokenUsage(entry.usage ?? undefined) ?? undefined,
      metadata: normalizeMessageMetadata(entry.metadata ?? undefined),
      _toolKind: tool?.kind,
      status: "done",
      timestamp: resolveEntryTimestamp(entry),
    };
  });

  const merged: ChatMessage[] = [];
  const callIdToMergedIndex: Record<string, number> = {};
  for (const cur of raw) {
    const { _toolKind, ...current } = cur;
    if (_toolKind === "call") {
      merged.push(current);
      const callId = current.toolData?.callId;
      if (callId) callIdToMergedIndex[callId] = merged.length - 1;
      continue;
    }
    if (_toolKind === "result") {
      const callId = current.toolData?.callId;
      const targetIdx = callId ? callIdToMergedIndex[callId] : undefined;
      if (targetIdx !== undefined) {
        const existing = merged[targetIdx];
        merged[targetIdx] = {
          ...existing,
          toolData: {
            ...existing.toolData,
            output: current.toolData?.output,
            errorCode: current.toolData?.errorCode,
            returnCode: current.toolData?.returnCode,
          },
          status: "done",
        };
        continue;
      }
    }
    merged.push(current);
  }

  // Roll up usage across a Turn so the UI reflects Turn-level totals.
  //
  // Context: inside a single Turn (one user -> agent round-trip), a ReAct
  // loop may invoke the LLM multiple times. Each provider response carries
  // its own usage_metadata, which would otherwise show as separate numbers
  // on intermediate tool-call bubbles and on the final reply bubble. That
  // makes the final bubble display ONLY the last model-call's usage, which
  // is misleading (users expect "how many tokens did this Turn cost").
  //
  // Strategy:
  //   1. Walk messages in order; every user message starts a new Turn.
  //   2. Sum every AI message's usage into a per-Turn accumulator and
  //      clear the individual AI usage so intermediate bubbles stay clean.
  //   3. When the Turn ends (next user message, or end of list), attach
  //      the accumulated usage to the Turn's final AI message. Preference
  //      is the last plain AI text (no toolData); otherwise fall back to
  //      the last AI message we saw.
  //   4. Also stash ``last_input_tokens`` = the *latest* call's input size
  //      (not the sum). Context-window ring must use that — summing N
  //      model calls easily exceeds the context limit and shows 100%.
  //
  // Net effect: the usage shown under the final reply equals the Turn's
  // run_usage (matches `[Token][Turn Summary]` server logs and
  // chat.meta.total_usage accumulation in turn_finalization.py).
  const emptyUsage = (): TokenUsage => ({
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  });
  let turnAcc: TokenUsage | null = null;
  let turnLastInputTokens = 0;
  let turnLastAiIdx: number | null = null;
  let turnLastPlainAiIdx: number | null = null;

  const flushTurn = () => {
    if (!turnAcc) return;
    const hasAny =
      (turnAcc.input_tokens || 0) > 0 ||
      (turnAcc.output_tokens || 0) > 0 ||
      (turnAcc.total_tokens || 0) > 0;
    if (hasAny) {
      const target = turnLastPlainAiIdx ?? turnLastAiIdx;
      if (target !== null) {
        merged[target] = {
          ...merged[target],
          usage: {
            ...turnAcc,
            ...(turnLastInputTokens > 0
              ? { last_input_tokens: turnLastInputTokens }
              : {}),
          },
        };
      }
    }
    turnAcc = null;
    turnLastInputTokens = 0;
    turnLastAiIdx = null;
    turnLastPlainAiIdx = null;
  };

  for (let i = 0; i < merged.length; i++) {
    const m = merged[i];
    if (m.role === "user") {
      flushTurn();
      turnAcc = emptyUsage();
      turnLastInputTokens = 0;
      continue;
    }
    if (m.role !== "assistant") continue;

    // Outside of any Turn (shouldn't happen for normal flows, but guard
    // against leading assistant messages from a proactive run).
    turnAcc ??= emptyUsage();

    const u = m.usage;
    if (u) {
      const callIn =
        typeof u.input_tokens === "number" && u.input_tokens > 0
          ? u.input_tokens
          : 0;
      if (callIn > 0) turnLastInputTokens = callIn;
      turnAcc.input_tokens =
        (turnAcc.input_tokens || 0) + (u.input_tokens || 0);
      turnAcc.output_tokens =
        (turnAcc.output_tokens || 0) + (u.output_tokens || 0);
      turnAcc.total_tokens =
        (turnAcc.total_tokens || 0) + (u.total_tokens || 0);
      // Strip the per-call usage so only the Turn's final bubble shows a total.
      merged[i] = { ...m, usage: undefined };
    }
    turnLastAiIdx = i;
    // A "plain" AI message is the final textual reply (no tool call).
    if (!m.toolData) {
      turnLastPlainAiIdx = i;
    }
  }
  flushTurn();

  return merged;
}

function toHistoryContentBlocks(content: unknown): unknown[] {
  if (Array.isArray(content)) return content;
  if (typeof content === "string" && content.trim()) {
    return [{ type: "text", text: content }];
  }
  return [];
}

function isDisplayableHistoryMessage(message: ChatMessage): boolean {
  if (message.toolData) return true;
  if (message.attachments && message.attachments.length > 0) return true;
  if (message.contentBlocks?.some((block) => block.content.trim())) return true;
  return message.content.trim().length > 0;
}

export function convertHistoryMessages(
  messages: Array<{
    role: string;
    content: unknown;
    id?: string;
    usage?: unknown;
    timestamp?: number;
    composer_context?: unknown;
    inbound_attachments?: unknown;
  }>,
  agentId?: string,
): ChatMessage[] {
  const entries: CallEntry[] = messages.map((message, index) => {
    const meta: Record<string, unknown> = {};
    if (message.composer_context) {
      meta.composer_context = message.composer_context;
    }
    if (message.inbound_attachments) {
      meta.inbound_attachments = message.inbound_attachments;
    }
    return {
      message_id: message.id,
      entry_index: `hist-${index}`,
      role: message.role,
      content: toHistoryContentBlocks(message.content),
      usage: normalizeTokenUsage(message.usage ?? undefined),
      timestamp:
        typeof message.timestamp === "number" ? message.timestamp : undefined,
      metadata: Object.keys(meta).length > 0 ? meta : undefined,
    };
  });
  const converted = convertCallEntries(entries).filter(
    isDisplayableHistoryMessage,
  );
  return agentId ? enrichAttachmentPreviewUrls(converted, agentId) : converted;
}

// ── Helpers ───────────────────────────────────────────────────────────────

async function loadThreadHistory(
  agentId: string,
  threadId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<{ messages: ChatMessage[]; hasMore: boolean; nextOffset: number }> {
  try {
    const { octopThreadsApi, CHAT_HISTORY_PAGE_SIZE } = await import(
      "../../../api/modules/octopThreads"
    );
    const limit = params.limit ?? CHAT_HISTORY_PAGE_SIZE;
    const offset = params.offset ?? 0;
    const history = await octopThreadsApi.history(agentId, threadId, {
      limit,
      offset,
    });
    const messages = convertHistoryMessages(
      history.messages.filter(
        (message) =>
          message.role === "user" ||
          message.role === "assistant" ||
          message.role === "tool",
      ),
      agentId,
    );
    return {
      messages,
      hasMore: Boolean(history.has_more),
      nextOffset: offset + limit,
    };
  } catch (err) {
    console.error("loadThreadHistory failed", err);
    return { messages: [], hasMore: false, nextOffset: 0 };
  }
}

// ── The hook ──────────────────────────────────────────────────────────────

/**
 * useChat delegates WebSocket streaming and message storage to the module-level
 * chatStore. This means messages and in-flight streams survive component
 * unmount/remount cycles (e.g. navigating away and back).
 */
export function useChat(
  sessionId: string | null,
  agentId: string | null = null,
) {
  const stableSessionId = sessionId || "__empty__";

  // Subscribe to the external store for this session
  const subscribeStore = useCallback(
    (cb: () => void) => chatStore.subscribe(stableSessionId, cb),
    [stableSessionId],
  );
  const getStoreSnapshot = useCallback(
    () => chatStore.getSnapshot(stableSessionId),
    [stableSessionId],
  );
  const {
    messages,
    isStreaming,
    thinkingStartedAt,
    runUsage,
    contextUsage,
    historyHasMore,
    historyLoadingMore,
  } = useSyncExternalStore(subscribeStore, getStoreSnapshot);

  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyRefreshing, setHistoryRefreshing] = useState(false);
  const loadGenRef = useRef(0);
  const loadMoreInFlightRef = useRef(false);
  const refreshInFlightRef = useRef(false);

  const sendMessage = useCallback(
    (
      text: string,
      _sessionKey: string,
      agentId: string,
      attachments?: ChatAttachment[],
      storeKey?: string,
      modelRef?: string | null,
      mcpServers?: string[] | null,
      skills?: string[] | null,
      targetAgentIds?: string[] | null,
      composerContext?: UserComposerContext,
    ) => {
      const key = storeKey || stableSessionId;

      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: text,
        attachments:
          attachments && attachments.length > 0 ? attachments : undefined,
        composerContext,
        status: "done",
        timestamp: Date.now(),
      };
      chatStore.appendUserMessage(key, userMsg);

      const threadIdForApi =
        storeKey ||
        (stableSessionId !== "__empty__" ? stableSessionId : undefined);
      chatStore.sendTurn(
        key,
        text,
        agentId,
        "",
        attachments,
        undefined,
        modelRef,
        threadIdForApi,
        mcpServers,
        skills,
        targetAgentIds,
      );
    },
    [stableSessionId],
  );

  const cancelStream = useCallback(() => {
    chatStore.cancelStream(stableSessionId);
  }, [stableSessionId]);

  const loadHistory = useCallback(
    async (targetThreadId: string) => {
      const key = targetThreadId || "__empty__";
      const snap = chatStore.getSnapshot(key);
      if (snap.isStreaming) return;

      chatStore.cancelStream(key);

      if (!targetThreadId || !agentId) {
        chatStore.clearMessages(key);
        return;
      }

      // Reuse in-memory messages when returning to a thread (no full reload).
      if (snap.messages.length > 0) {
        return;
      }

      const gen = ++loadGenRef.current;
      setHistoryLoading(true);

      try {
        const {
          messages: converted,
          hasMore,
          nextOffset,
        } = await loadThreadHistory(agentId, targetThreadId, { offset: 0 });
        if (loadGenRef.current !== gen) return;
        chatStore.setHistoryPage(key, converted, {
          hasMore,
          nextOffset,
        });
      } finally {
        if (loadGenRef.current === gen) {
          setHistoryLoading(false);
        }
      }
    },
    [agentId],
  );

  const loadMoreHistory = useCallback(async (): Promise<boolean> => {
    const key = stableSessionId;
    const snap = chatStore.getSnapshot(key);
    if (
      loadMoreInFlightRef.current ||
      snap.historyLoadingMore ||
      !snap.historyHasMore ||
      snap.isStreaming ||
      !agentId ||
      stableSessionId === "__empty__"
    ) {
      return false;
    }

    loadMoreInFlightRef.current = true;
    chatStore.setHistoryLoadingMore(key, true);
    const offset = snap.historyNextOffset;

    try {
      const {
        messages: older,
        hasMore,
        nextOffset,
      } = await loadThreadHistory(agentId, stableSessionId, { offset });
      chatStore.prependHistoryMessages(key, older, { hasMore, nextOffset });
      return true;
    } finally {
      loadMoreInFlightRef.current = false;
      chatStore.setHistoryLoadingMore(key, false);
    }
  }, [agentId, stableSessionId]);

  /**
   * Force-reload the latest history page from the API.
   *
   * Used when the user overscrolls at the bottom to recover from a dropped WS
   * stream that left the last assistant turn incomplete in memory.
   */
  const refreshHistory = useCallback(async () => {
    const key = stableSessionId;
    const snap = chatStore.getSnapshot(key);
    if (
      refreshInFlightRef.current ||
      historyRefreshing ||
      historyLoading ||
      snap.isStreaming ||
      !agentId ||
      key === "__empty__"
    ) {
      return;
    }

    refreshInFlightRef.current = true;
    const gen = ++loadGenRef.current;
    setHistoryRefreshing(true);

    try {
      const {
        messages: latest,
        hasMore,
        nextOffset,
      } = await loadThreadHistory(agentId, key, { offset: 0 });
      if (loadGenRef.current !== gen) return;

      // Keep older pages the user already scrolled in; replace the overlapping
      // latest-page window with the server copy so truncated WS turns heal.
      const latestIds = new Set(latest.map((m) => m.id));
      const firstOverlap = snap.messages.findIndex((m) => latestIds.has(m.id));
      const olderPrefix =
        firstOverlap > 0 ? snap.messages.slice(0, firstOverlap) : [];
      chatStore.setHistoryPage(key, [...olderPrefix, ...latest], {
        hasMore: olderPrefix.length > 0 ? snap.historyHasMore : hasMore,
        nextOffset:
          olderPrefix.length > 0 ? snap.historyNextOffset : nextOffset,
      });
    } finally {
      refreshInFlightRef.current = false;
      if (loadGenRef.current === gen) {
        setHistoryRefreshing(false);
      }
    }
  }, [agentId, stableSessionId, historyRefreshing, historyLoading]);

  /**
   * Edit a historical user message: truncate everything from that message
   * onwards, replace its content, then re-send to the backend.
   * Mirrors the behaviour of Claude / ChatGPT "edit message".
   */
  const editAndResend = useCallback(
    (
      messageId: string,
      newText: string,
      _sessionKey: string,
      agentId: string,
    ) => {
      const ok = chatStore.truncateAndReplaceUserMessage(
        stableSessionId,
        messageId,
        newText,
      );
      if (!ok) return;

      // Re-send without appending a new user message — it is already in the store
      chatStore.sendTurn(
        stableSessionId,
        newText,
        agentId,
        "",
        undefined,
        undefined,
        undefined,
        stableSessionId !== "__empty__" ? stableSessionId : undefined,
      );
    },
    [stableSessionId],
  );

  const clearMessages = useCallback(() => {
    chatStore.clearMessages(stableSessionId);
  }, [stableSessionId]);

  const resumeHitl = useCallback(
    (
      decisions: Array<{ type: string; message?: string }>,
      storeKey?: string,
    ) => {
      if (!agentId) return;
      const key = storeKey || stableSessionId;
      const threadId =
        storeKey || (stableSessionId !== "__empty__" ? stableSessionId : "");
      if (!threadId || threadId === "__empty__") return;
      void chatStore.resumeHitl(key, agentId, threadId, decisions);
    },
    [agentId, stableSessionId],
  );

  return {
    messages,
    isStreaming,
    thinkingStartedAt,
    runUsage,
    contextUsage,
    historyLoading,
    historyHasMore,
    historyLoadingMore,
    historyRefreshing,
    sendMessage,
    editAndResend,
    cancelStream,
    loadHistory,
    loadMoreHistory,
    refreshHistory,
    clearMessages,
    resumeHitl,
  };
}
