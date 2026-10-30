import { useCallback, useEffect } from "react";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import type { ChatAttachment, UserComposerContext } from "./useChat";
import {
  isPendingThread,
  syncSessionHitlPolicy,
  type Session,
} from "./useSessions";
import type { HitlSessionPolicy } from "../utils/hitlSessionPolicy";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "../constants";
import { message } from "@/utils/antdMessage";

import {
  buildComposerContext,
  buildUserMessage,
  resolveTurnModelRef,
} from "../utils/chatMessages";
import { parseSkillSlugsInText } from "../utils/skillSlash";

interface UseChatSendParams {
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  selectedModel: string | null;
  selectedConnectors: string[];
  selectedKnowledgeBaseIds: string[];
  selectedTargetAgents?: string[];
  reasoningMode: "auto" | "enabled" | "disabled";
  reasoningEffort: string | null;
  conversationMode?: "ask" | "plan" | "craft";
  hitlPolicy?: HitlSessionPolicy;
  defaultModel?: string | null;
  sendMessage: (
    text: string,
    sessionKey: string,
    agentId: string,
    attachments?: ChatAttachment[],
    storeKey?: string,
    modelRef?: string | null,
    mcpServers?: string[] | null,
    knowledgeBaseIds?: string[] | null,
    targetAgentIds?: string[] | null,
    composerContext?: UserComposerContext,
    reasoningMode?: "auto" | "enabled" | "disabled",
    reasoningEffort?: string | null,
    conversationMode?: "ask" | "plan" | "craft" | null,
    hitlPolicy?: HitlSessionPolicy | null,
  ) => void;
  createSession: () => { session: Session; resolvedId: Promise<string> };
  /** Called when auto-recording starts successfully from a pending message. */
  onAutoRecordingStarted?: (recordingId: string) => void;
  t: TFunction;
}

/** Optional composer snapshot used when flushing a queued message. */
export type ChatSendOverrides = {
  selectedModel?: string | null;
  selectedConnectors?: string[];
  selectedKnowledgeBaseIds?: string[];
  selectedTargetAgents?: string[];
  composerContext?: UserComposerContext;
  modelRef?: string | null;
  /** Send to this thread instead of the active one (queued flush). */
  threadId?: string | null;
  /** Send as this agent instead of the active one (queued flush). */
  agentId?: string | null;
  conversationMode?: "ask" | "plan" | "craft";
  hitlPolicy?: HitlSessionPolicy;
};

export function useChatSend({
  resolvedAgentId,
  activeThreadId,
  selectedModel,
  selectedConnectors,
  selectedKnowledgeBaseIds,
  selectedTargetAgents = [],
  reasoningMode,
  reasoningEffort,
  conversationMode = "craft",
  hitlPolicy,
  defaultModel,
  sendMessage,
  createSession,
  onAutoRecordingStarted,
  t,
}: UseChatSendParams) {
  const navigate = useNavigate();

  /** @returns false when the send was rejected before starting a turn. */
  const handleSend = useCallback(
    (
      text: string,
      attachments?: ChatAttachment[],
      overrides?: ChatSendOverrides,
    ): boolean => {
      const agent = overrides?.agentId ?? resolvedAgentId;
      if (!agent) {
        message.warning(t("chat.pickAgent", "请先选择一个 Agent"));
        return false;
      }

      const trimmed = text.trim();
      if (!trimmed && !(attachments && attachments.length > 0)) return false;

      const mode = overrides?.conversationMode ?? conversationMode;
      const policy = overrides?.hitlPolicy ?? hitlPolicy;
      const restricted = mode === "ask" || mode === "plan";
      const connectors = restricted
        ? []
        : overrides?.selectedConnectors ?? selectedConnectors;
      const knowledgeBaseIds =
        overrides?.selectedKnowledgeBaseIds ?? selectedKnowledgeBaseIds;
      const targetAgents = restricted
        ? []
        : overrides?.selectedTargetAgents ?? selectedTargetAgents;
      const modelSelection =
        overrides?.selectedModel !== undefined
          ? overrides.selectedModel
          : selectedModel;

      const composerContext =
        overrides?.composerContext ??
        buildComposerContext({
          skills: restricted ? [] : parseSkillSlugsInText(trimmed),
          connectors,
          knowledgeBaseIds,
          targetAgents,
          selectedModel: modelSelection,
          reasoningMode:
            overrides?.composerContext?.reasoningMode ?? reasoningMode,
          reasoningEffort:
            overrides?.composerContext?.reasoningEffort ?? reasoningEffort,
        });

      const modelOverride =
        overrides?.modelRef !== undefined
          ? overrides.modelRef
          : resolveTurnModelRef(modelSelection, defaultModel);

      const runSend = (tid: string) => {
        sendMessage(
          trimmed,
          "",
          agent,
          attachments,
          tid,
          modelOverride,
          connectors,
          knowledgeBaseIds,
          targetAgents,
          composerContext,
          composerContext?.reasoningMode ?? reasoningMode,
          composerContext?.reasoningEffort ?? reasoningEffort,
          mode,
          policy,
        );
      };

      const targetThreadId =
        overrides?.threadId !== undefined ? overrides.threadId : activeThreadId;

      if (targetThreadId) {
        if (isPendingThread(targetThreadId)) {
          message.info(t("chat.creatingSession", "正在创建会话，请稍候"));
          return false;
        }
        runSend(targetThreadId);
        return true;
      }

      const userMsg = buildUserMessage(trimmed, attachments, composerContext);
      chatStore.appendUserMessage(EMPTY_CHAT_SESSION_KEY, userMsg);

      const { resolvedId } = createSession();
      const snap = chatStore.getSnapshot(EMPTY_CHAT_SESSION_KEY);
      // Break any leftover ``__pending__`` → previous thr_* alias so this new
      // chat cannot mutate / stream into an older thread's bucket.
      chatStore.detachSessionKey(PENDING_THREAD_ID);
      chatStore.setMessages(PENDING_THREAD_ID, snap.messages);
      chatStore.clearMessages(EMPTY_CHAT_SESSION_KEY);
      navigate(`/chat/${agent}/${PENDING_THREAD_ID}`);

      void resolvedId.then((tid) => {
        if (!tid) {
          chatStore.clearMessages(PENDING_THREAD_ID);
          navigate(`/chat/${agent}`, { replace: true });
          message.error(t("chat.createSessionFailed", "创建会话失败，请重试"));
          return;
        }
        chatStore.renameSessionKey(PENDING_THREAD_ID, tid);
        // Title is filled by the server from an AI summary of this first
        // message. Do not lock the raw question in as the thread name.
        if (policy) syncSessionHitlPolicy(tid, policy);
        chatStore.sendTurn(
          tid,
          trimmed,
          agent,
          "",
          attachments,
          undefined,
          modelOverride,
          tid,
          connectors,
          knowledgeBaseIds,
          targetAgents,
          composerContext?.reasoningMode ?? reasoningMode,
          composerContext?.reasoningEffort ?? reasoningEffort,
          mode,
          policy,
          userMsg.id,
        );
        navigate(`/chat/${agent}/${tid}`, { replace: true });
      });
      return true;
    },
    [
      activeThreadId,
      sendMessage,
      createSession,
      navigate,
      resolvedAgentId,
      selectedModel,
      selectedConnectors,
      selectedKnowledgeBaseIds,
      selectedTargetAgents,
      reasoningMode,
      reasoningEffort,
      conversationMode,
      hitlPolicy,
      defaultModel,
      t,
    ],
  );

  useEffect(() => {
    const consumePending = () => {
      const raw = localStorage.getItem("octop.pendingChatMessage");
      if (!raw) return;
      localStorage.removeItem("octop.pendingChatMessage");

      let textToSend = raw;
      let autoRecord = false;

      // Support JSON format: { text, agentId, autoRecord }
      try {
        const parsed = JSON.parse(raw);
        if (typeof parsed === "object" && parsed.text) {
          textToSend = parsed.text;
          autoRecord = Boolean(parsed.autoRecord);
        }
      } catch {
        // Not JSON — treat as plain text (legacy format)
      }

      setTimeout(() => handleSend(textToSend), 500);

      // If autoRecord flag is set, start browser recording after sending the message
      if (autoRecord) {
        setTimeout(async () => {
          try {
            const { browserApi } = await import("../../../api/modules/browser");
            const data = await browserApi.startRecording({
              name: activeThreadId
                ? `chat-${activeThreadId}`
                : "skill-recording",
            });
            if (data.ok) {
              // Notify the chat page that recording has started (update UI state)
              if (data.recordingId && onAutoRecordingStarted) {
                onAutoRecordingStarted(data.recordingId);
              }
              // Push a system message into the chat about recording started
              const { generateId } = await import(
                "../../../utils/messageParser"
              );
              const pushMsg = {
                id: generateId(),
                role: "assistant" as const,
                content: t("skillRecord.recordingStartedMessage"),
                timestamp: Date.now(),
                status: "done" as const,
              };
              // Append directly to chat store
              const { appendPushMessage } = await import("./chatStore");
              appendPushMessage(pushMsg.content);
            }
          } catch {
            // Silently ignore recording start failure; the user can manually start
          }
        }, 1500);
      }
    };

    consumePending();

    const handler = () => consumePending();
    window.addEventListener("octop:pending-chat-message", handler);
    return () =>
      window.removeEventListener("octop:pending-chat-message", handler);
  }, [handleSend, activeThreadId, onAutoRecordingStarted, t]);

  return { handleSend };
}
