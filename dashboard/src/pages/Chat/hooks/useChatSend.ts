import { useCallback, useEffect } from "react";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import type { ChatAttachment, UserComposerContext } from "./useChat";
import { isPendingThread, type Session } from "./useSessions";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "../constants";
import { message } from "@/utils/antdMessage";

import {
  buildComposerContext,
  buildUserMessage,
  resolveTurnModelRef,
} from "../utils/chatMessages";

interface UseChatSendParams {
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  selectedModel: string | null;
  selectedConnectors: string[];
  selectedKnowledgeBaseIds: string[];
  selectedSkills: string[];
  selectedTargetAgents: string[];
  reasoningMode: "auto" | "enabled" | "disabled";
  reasoningEffort: string | null;
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
    skills?: string[] | null,
    targetAgentIds?: string[] | null,
    composerContext?: UserComposerContext,
    reasoningMode?: "auto" | "enabled" | "disabled",
    reasoningEffort?: string | null,
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
  selectedSkills?: string[];
  selectedTargetAgents?: string[];
  composerContext?: UserComposerContext;
  modelRef?: string | null;
  /** Send to this thread instead of the active one (queued flush). */
  threadId?: string | null;
  /** Send as this agent instead of the active one (queued flush). */
  agentId?: string | null;
};

export function useChatSend({
  resolvedAgentId,
  activeThreadId,
  selectedModel,
  selectedConnectors,
  selectedKnowledgeBaseIds,
  selectedSkills,
  selectedTargetAgents,
  reasoningMode,
  reasoningEffort,
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

      const skills = overrides?.selectedSkills ?? selectedSkills;
      const connectors = overrides?.selectedConnectors ?? selectedConnectors;
      const knowledgeBaseIds =
        overrides?.selectedKnowledgeBaseIds ?? selectedKnowledgeBaseIds;
      const targetAgents =
        overrides?.selectedTargetAgents ?? selectedTargetAgents;
      const modelSelection =
        overrides?.selectedModel !== undefined
          ? overrides.selectedModel
          : selectedModel;

      const composerContext =
        overrides?.composerContext ??
        buildComposerContext({
          skills,
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
          skills,
          targetAgents,
          composerContext,
          composerContext?.reasoningMode ?? reasoningMode,
          composerContext?.reasoningEffort ?? reasoningEffort,
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
          skills,
          targetAgents,
          composerContext?.reasoningMode ?? reasoningMode,
          composerContext?.reasoningEffort ?? reasoningEffort,
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
      selectedSkills,
      selectedTargetAgents,
      reasoningMode,
      reasoningEffort,
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
            const profile = activeThreadId || "default";
            const data = await browserApi.startRecording({
              profile,
              agentProfile: profile,
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
                content: `🎬 录制已开始！请在浏览器中进行你想要自动化的操作。\n\n操作完成后，输入"结束"即可结束录制，系统将自动生成技能脚本。`,
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
  }, [handleSend, activeThreadId, onAutoRecordingStarted]);

  return { handleSend };
}
