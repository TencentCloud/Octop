import { useCallback, useEffect } from "react";
import { message } from "antd";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import type { ChatAttachment, UserComposerContext } from "./useChat";
import type { Session } from "./useSessions";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "../constants";
import {
  buildComposerContext,
  buildUserMessage,
  resolveTurnModelRef,
} from "../utils/chatMessages";

interface UseChatSendParams {
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  sessions: Session[];
  messagesLength: number;
  selectedModel: string | null;
  selectedConnectors: string[];
  selectedSkills: string[];
  selectedTargetAgents: string[];
  defaultModel?: string | null;
  sendMessage: (
    text: string,
    sessionKey: string,
    agentId: string,
    attachments?: ChatAttachment[],
    storeKey?: string,
    modelRef?: string | null,
    mcpServers?: string[] | null,
    skills?: string[] | null,
    targetAgentIds?: string[] | null,
    composerContext?: UserComposerContext,
  ) => void;
  createSession: () => { session: Session; resolvedId: Promise<string> };
  renameSession: (id: string, name: string) => void;
  /** Called when auto-recording starts successfully from a pending message. */
  onAutoRecordingStarted?: (recordingId: string) => void;
  t: TFunction;
}

function deriveThreadTitle(msg: string): string {
  const normalized = msg
    .replace(/[\r\n]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return normalized.length > 40 ? `${normalized.slice(0, 39)}…` : normalized;
}

export function useChatSend({
  resolvedAgentId,
  activeThreadId,
  sessions,
  messagesLength,
  selectedModel,
  selectedConnectors,
  selectedSkills,
  selectedTargetAgents,
  defaultModel,
  sendMessage,
  createSession,
  renameSession,
  onAutoRecordingStarted,
  t,
}: UseChatSendParams) {
  const navigate = useNavigate();

  const handleSend = useCallback(
    (text: string, attachments?: ChatAttachment[]) => {
      const agent = resolvedAgentId;
      if (!agent) {
        message.warning(t("chat.pickAgent", "请先选择一个 Agent"));
        return;
      }

      const trimmed = text.trim();
      if (!trimmed && !(attachments && attachments.length > 0)) return;

      const maybeRenameNewThread = (tid: string, hadMessages: boolean) => {
        const current = sessions.find((s) => s.id === tid);
        if (current?.name === "New Chat" && !hadMessages) {
          renameSession(tid, deriveThreadTitle(trimmed));
        }
      };

      const composerContext = buildComposerContext({
        skills: selectedSkills,
        connectors: selectedConnectors,
        targetAgents: selectedTargetAgents,
        selectedModel,
      });

      const modelOverride = resolveTurnModelRef(selectedModel, defaultModel);

      const runSend = (tid: string, hadMessages: boolean) => {
        maybeRenameNewThread(tid, hadMessages);
        sendMessage(
          trimmed,
          "",
          agent,
          attachments,
          tid,
          modelOverride,
          selectedConnectors,
          selectedSkills,
          selectedTargetAgents,
          composerContext,
        );
      };

      if (activeThreadId) {
        runSend(activeThreadId, messagesLength > 0);
        return;
      }

      const userMsg = buildUserMessage(trimmed, attachments, composerContext);
      chatStore.appendUserMessage(EMPTY_CHAT_SESSION_KEY, userMsg);

      const { resolvedId } = createSession();
      const snap = chatStore.getSnapshot(EMPTY_CHAT_SESSION_KEY);
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
        const currentSnap = chatStore.getSnapshot(PENDING_THREAD_ID);
        const hadMessages = currentSnap.messages.length > 1;
        chatStore.renameSessionKey(PENDING_THREAD_ID, tid);
        maybeRenameNewThread(tid, hadMessages);
        chatStore.sendTurn(
          tid,
          trimmed,
          agent,
          "",
          attachments,
          undefined,
          modelOverride,
          tid,
          selectedConnectors,
          selectedSkills,
          selectedTargetAgents,
        );
        navigate(`/chat/${agent}/${tid}`, { replace: true });
      });
    },
    [
      activeThreadId,
      sessions,
      messagesLength,
      sendMessage,
      createSession,
      renameSession,
      navigate,
      resolvedAgentId,
      selectedModel,
      selectedConnectors,
      selectedSkills,
      selectedTargetAgents,
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
