import { useCallback, useRef, useState } from "react";
import { Button, Spin, Tooltip } from "antd";
import { Bot, Send, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OctopAgent } from "../context/AgentContext";
import AgentSelector from "./AgentSelector";
import { useAgentThreadChat } from "../hooks/useAgentThreadChat";
import MessageList from "../pages/Chat/components/MessageList";
import chatStyles from "../pages/Chat/index.module.less";
import styles from "./BrowserAiPanel.module.less";

export interface MobileAiPanelProps {
  activeAgent: OctopAgent | null;
  device: string | null;
  deviceName?: string | null;
  /** True while a Remote Phone stream session is open (agent may use the device). */
  streamActive: boolean;
  onClose: () => void;
  layout?: "right" | "bottom";
}

/**
 * Agent chat side panel for Remote Phone (mirrors Browser AI chrome, phone context).
 */
export default function MobileAiPanel({
  activeAgent,
  device,
  deviceName,
  streamActive,
  onClose,
  layout = "right",
}: MobileAiPanelProps) {
  const { t } = useTranslation();
  const panelClassName = `${styles.panel}${
    layout === "bottom" ? ` ${styles.panelBottom}` : ""
  }`;
  const [inputValue, setInputValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imeComposingRef = useRef(false);

  const agentId = activeAgent?.agent_id ?? null;
  const {
    threadId,
    booting,
    bootError,
    messages,
    isStreaming,
    send,
    cancelStream,
  } = useAgentThreadChat(agentId);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming || !activeAgent) return;
    setInputValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    send(text);
  }, [activeAgent, inputValue, isStreaming, send]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      if (
        imeComposingRef.current ||
        e.nativeEvent.isComposing ||
        e.keyCode === 229
      )
        return;
      e.preventDefault();
      handleSend();
    },
    [handleSend],
  );

  const handleTextareaInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    },
    [],
  );

  if (!activeAgent) {
    return (
      <div className={panelClassName}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <Bot size={14} />
            <span>{t("remoteAndroid.ai.title", "AI 助手")}</span>
          </div>
          <Tooltip title={t("common.close", "关闭")}>
            <Button
              type="text"
              size="small"
              icon={<X size={14} />}
              onClick={onClose}
            />
          </Tooltip>
        </div>
        <div className={styles.emptyState}>
          <Bot size={30} color="var(--fn-text-quaternary, #9ca3af)" />
          <div className={styles.emptyTitle}>
            {t("remoteAndroid.ai.noAgentTitle", "请选择一个 Agent")}
          </div>
          <div className={styles.emptyDesc}>
            {t(
              "remoteAndroid.ai.noAgentDesc",
              "远程手机右侧助手会复用当前 Agent 的对话能力。连接手机后，Agent 即可操作该设备。",
            )}
          </div>
          <div className={styles.emptyAgentPicker}>
            <AgentSelector variant="select" showLabel={false} />
          </div>
        </div>
      </div>
    );
  }

  const none = t("remoteAndroid.infoNone", "—");

  return (
    <div className={panelClassName}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>
          <Bot size={14} />
          <span>{t("remoteAndroid.ai.title", "AI 助手")}</span>
        </div>
        <div className={styles.headerActions}>
          <Tooltip title={t("common.close", "关闭")}>
            <Button
              type="text"
              size="small"
              icon={<X size={14} />}
              onClick={onClose}
            />
          </Tooltip>
        </div>
      </div>

      <div className={styles.contextSection}>
        <div className={styles.expertSelectRow}>
          <span className={styles.contextLabel}>
            {t("remoteAndroid.ai.expert", "专家")}
          </span>
          <AgentSelector variant="select" showLabel={false} />
        </div>
        <div className={styles.contextGrid}>
          <span className={styles.contextLabel}>
            {t("remoteAndroid.ai.device", "设备")}
          </span>
          <span
            className={styles.contextValue}
            title={deviceName || device || undefined}
          >
            {deviceName || device || none}
          </span>
          <span className={styles.contextLabel}>
            {t("remoteAndroid.ai.serial", "序列号")}
          </span>
          <span className={styles.contextValue}>{device || none}</span>
          <span className={styles.contextLabel}>
            {t("remoteAndroid.ai.session", "会话")}
          </span>
          <span className={styles.contextValue}>
            {streamActive
              ? t("remoteAndroid.ai.sessionActive", "已连接（Agent 可用）")
              : t("remoteAndroid.ai.sessionIdle", "未连接")}
          </span>
        </div>
      </div>

      <div className={`${styles.messages} ${chatStyles.messageListWrapper}`}>
        {booting ? (
          <div className={styles.messagesLoading}>
            <Spin size="small" />
          </div>
        ) : bootError ? (
          <div className={styles.messagesError}>{bootError}</div>
        ) : (
          <MessageList
            messages={messages}
            isStreaming={isStreaming}
            sessionKey={threadId ?? undefined}
            onCancel={cancelStream}
          />
        )}
      </div>

      <div className={styles.sendBar}>
        <div className={styles.sendRow}>
          <textarea
            ref={textareaRef}
            className={styles.sendTextarea}
            value={inputValue}
            onCompositionStart={() => {
              imeComposingRef.current = true;
            }}
            onCompositionEnd={() => {
              imeComposingRef.current = false;
            }}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder={t(
              "remoteAndroid.ai.inputPlaceholder",
              "让 Agent 在手机上操作，或询问当前屏幕…",
            )}
            rows={1}
            disabled={isStreaming || booting}
          />
          <button
            type="button"
            className={styles.sendBtn}
            disabled={!inputValue.trim() || isStreaming || booting}
            onClick={handleSend}
            title={t("terminal.ai.send", "发送")}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
