import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button, Tooltip, Tag, Spin } from "antd";
import { Bot, X, Square, Play, Loader2, Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message as antMessage } from "antd";

import type { OctopAgent } from "../context/AgentContext";
import AgentSelector from "../components/AgentSelector";
import { useAgentThreadChat } from "../hooks/useAgentThreadChat";
import { browserApi } from "../api/modules/browser";
import { request } from "../api/request";
import MessageList from "../pages/Chat/components/MessageList";
import * as chatStore from "../pages/Chat/hooks/chatStore";
import chatStyles from "../pages/Chat/index.module.less";
import styles from "./BrowserAiPanel.module.less";

export interface BrowserAiTabContext {
  id: number | string;
  url: string;
  title: string;
  active: boolean;
}

interface BrowserAiPanelProps {
  activeAgent: OctopAgent | null;
  tabs: BrowserAiTabContext[];
  currentUrl: string;
  profileId?: string | null;
  onClose: () => void;
  layout?: "right" | "bottom";
  /** Skill recording state from parent (RemoteBrowserPage) */
  browserRecording?: boolean;
  browserRecordingId?: string | null;
  browserLastRecordingId?: string | null;
  setBrowserRecording?: (v: boolean) => void;
  setBrowserRecordingId?: (v: string | null) => void;
  setBrowserLastRecordingId?: (v: string | null) => void;
  /** Skill name (task objective) — used as the trigger keyword */
  skillName?: string;
  /** Callback in parent to persist the skill name when user sets it in chat */
  onSkillNameSet?: (name: string) => void;
  /** Whether a browser session is currently active */
  browserSessionActive?: boolean;
  /** Whether a browser session is currently being started */
  browserStarting?: boolean;
  /** Callback to start a browser session */
  onStartBrowser?: () => void;
}

// Keywords that trigger "stop recording and generate skill"
const END_KEYWORDS = ["结束", "end", "stop recording", "结束录制"];

// Keywords that trigger "confirm and apply skill"
const CONFIRM_KEYWORDS = ["确认", "confirm", "ok", "确认应用", "apply"];

type RecordingPhase =
  | "idle"
  | "awaitObjective"
  | "awaitDescription"
  | "recording";

export default function BrowserAiPanel({
  activeAgent,
  tabs,
  currentUrl,
  profileId,
  onClose,
  layout = "right",
  browserRecording = false,
  browserRecordingId = null,
  browserLastRecordingId = null,
  setBrowserRecording,
  setBrowserRecordingId,
  setBrowserLastRecordingId,
  skillName = "",
  onSkillNameSet,
}: BrowserAiPanelProps) {
  const { t } = useTranslation();
  const panelClassName = `${styles.panel}${
    layout === "bottom" ? ` ${styles.panelBottom}` : ""
  }`;
  const [inputValue, setInputValue] = useState("");
  const [browserReplayBusy, setBrowserReplayBusy] = useState(false);
  const [pendingSkillContent, setPendingSkillContent] = useState<string | null>(
    null,
  );
  const [pendingSkillName, setPendingSkillName] = useState<string | null>(null);
  const [, setPendingSkillRecordingId] = useState<string | null>(null);
  const workflowBusyRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imeComposingRef = useRef(false);

  // Recording workflow phase
  const [recordingPhase, setRecordingPhase] = useState<RecordingPhase>("idle");

  // Saved skill names for keyword-trigger replay
  const [savedSkillNames, setSavedSkillNames] = useState<string[]>([]);

  const activeTab = useMemo(() => tabs.find((tab) => tab.active), [tabs]);
  const agentId = activeAgent?.agent_id ?? null;

  // Load saved skill names from API on mount / agent change
  useEffect(() => {
    if (!agentId) {
      setSavedSkillNames([]);
      return;
    }
    void (async () => {
      try {
        const skills = await request<{ slug: string; name: string }[]>(
          `/agents/${agentId}/skills`,
        );
        if (Array.isArray(skills)) {
          setSavedSkillNames(skills.map((s) => s.slug ?? s.name));
        }
      } catch {
        // Non-critical
      }
    })();
  }, [agentId]);

  const {
    threadId,
    booting,
    bootError,
    messages,
    isStreaming,
    send,
    cancelStream,
  } = useAgentThreadChat(agentId);

  // When browserRecording transitions, sync phase
  useEffect(() => {
    if (browserRecording && recordingPhase === "idle") {
      setRecordingPhase("awaitObjective");
    }
    if (!browserRecording && recordingPhase !== "idle") {
      setRecordingPhase("idle");
    }
  }, [browserRecording, recordingPhase]);

  // --- Skill recording workflow ---
  const isEndRecordingCommand = useCallback(
    (text: string): boolean => {
      const normalized = text.trim().toLowerCase();
      return (
        browserRecording &&
        recordingPhase === "recording" &&
        END_KEYWORDS.some((kw) => normalized === kw.toLowerCase())
      );
    },
    [browserRecording, recordingPhase],
  );

  const isConfirmSkillCommand = useCallback(
    (text: string): boolean => {
      const normalized = text.trim().toLowerCase();
      return (
        !!pendingSkillContent &&
        CONFIRM_KEYWORDS.some((kw) => normalized === kw.toLowerCase())
      );
    },
    [pendingSkillContent],
  );

  const isSkillTriggerCommand = useCallback(
    (text: string): boolean => {
      const trimmed = text.trim();
      return (
        !browserRecording &&
        !pendingSkillContent &&
        savedSkillNames.some(
          (name) => name.toLowerCase() === trimmed.toLowerCase(),
        )
      );
    },
    [browserRecording, pendingSkillContent, savedSkillNames],
  );

  const handleObjectiveInput = useCallback(
    (text: string) => {
      const objective = text.trim();
      if (!objective) return;
      setInputValue("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      setPendingSkillName(objective);
      if (onSkillNameSet) onSkillNameSet(objective);
      setRecordingPhase("awaitDescription");
      chatStore.appendPushMessage(
        `✅ 任务目标已设定：**${objective}**\n\n` +
          "接下来请描述你想让AI助手在浏览器中执行的具体操作。\n\n" +
          `例如："打开B站、小红书和百度，搜索今天天气"。\n\n` +
          '描述完成后AI会自动执行操作；操作结束后输入"结束"即可停止录制。',
      );
    },
    [onSkillNameSet],
  );

  const handleDescriptionInput = useCallback(
    (text: string) => {
      const description = text.trim();
      setInputValue("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      setRecordingPhase("recording");
      send(description);
    },
    [send],
  );

  const handleEndRecording = useCallback(async () => {
    if (workflowBusyRef.current) return;
    workflowBusyRef.current = true;
    try {
      const effectiveSkillName =
        skillName || pendingSkillName || "browser-skill";
      const data = await browserApi.stopAndGenerateSkill({
        recordingId: browserRecordingId,
        name: effectiveSkillName,
        generateSteps: true,
      });
      const recordingId = data.recordingId ?? browserRecordingId;
      if (setBrowserRecording) setBrowserRecording(false);
      if (setBrowserRecordingId) setBrowserRecordingId(null);
      if (recordingId && setBrowserLastRecordingId)
        setBrowserLastRecordingId(recordingId);

      if (data.skillContent) {
        setPendingSkillContent(data.skillContent);
        setPendingSkillName(effectiveSkillName);
        setPendingSkillRecordingId(recordingId ?? null);

        const previewLines = data.skillContent.split("\n").slice(0, 20);
        const previewText = previewLines.join("\n");
        const truncationNotice =
          data.skillContent.split("\n").length > 20
            ? `\n\n... (共 ${
                data.skillContent.split("\n").length
              } 行，完整内容将在确认后保存)`
            : "";
        chatStore.appendPushMessage(
          `✅ 录制完成！已生成 ${data.steps ?? 0} 个回放步骤。\n\n` +
            `📝 **技能「${effectiveSkillName}」脚本预览：**\n\n${previewText}${truncationNotice}\n\n` +
            '回复"确认"即可应用此技能。\n\n' +
            `应用后，只需输入 **"${effectiveSkillName}"** 即可一键触发回放相同操作流程。`,
        );
      } else {
        chatStore.appendPushMessage(
          `✅ 录制完成！已生成 ${data.steps ?? 0} 个回放步骤。\n\n` +
            `⚠️ 技能脚本生成失败，请稍后重试。`,
        );
      }
      antMessage.success(`录制完成，已生成 ${data.steps ?? 0} 个回放步骤`);
    } catch (err) {
      antMessage.error(err instanceof Error ? err.message : "停止录制失败");
    } finally {
      workflowBusyRef.current = false;
    }
  }, [
    browserRecordingId,
    skillName,
    pendingSkillName,
    setBrowserRecording,
    setBrowserRecordingId,
    setBrowserLastRecordingId,
  ]);

  const handleConfirmSkill = useCallback(async () => {
    if (
      !pendingSkillContent ||
      !pendingSkillName ||
      !agentId ||
      workflowBusyRef.current
    )
      return;
    workflowBusyRef.current = true;
    try {
      const result = await request<{
        slug: string;
        name: string;
        enabled: boolean;
      }>(`/agents/${agentId}/skills`, {
        method: "POST",
        body: JSON.stringify({
          name: pendingSkillName,
          content: pendingSkillContent,
        }),
      });
      const finalName = result.slug || result.name || pendingSkillName;
      setPendingSkillContent(null);
      setPendingSkillName(null);
      setPendingSkillRecordingId(null);
      setSavedSkillNames((prev) =>
        prev.includes(finalName) ? prev : [...prev, finalName],
      );
      chatStore.appendPushMessage(
        `🎉 技能 **「${finalName}」** 已成功应用！\n\n` +
          `之后只需输入 **"${finalName}"** 即可一键触发回放相同的浏览器操作流程。`,
      );
      antMessage.success(`技能 "${finalName}" 已成功应用`);
    } catch (err) {
      antMessage.error(err instanceof Error ? err.message : "应用技能失败");
    } finally {
      workflowBusyRef.current = false;
    }
  }, [pendingSkillContent, pendingSkillName, agentId]);

  const handleSkillReplay = useCallback(
    async (skillKeyword: string) => {
      if (workflowBusyRef.current) return;
      workflowBusyRef.current = true;
      setBrowserReplayBusy(true);
      try {
        const skillDetail = await request<{ body: string; raw: string }>(
          `/agents/${agentId}/skills/${encodeURIComponent(skillKeyword)}`,
        );
        const rawContent = skillDetail.raw || skillDetail.body || "";
        const recordingIdMatch = rawContent.match(
          /recording[_\s-]*id[:\s]*`?([a-zA-Z0-9_-]+)`?/i,
        );
        const recordingId = recordingIdMatch?.[1] ?? browserLastRecordingId;
        if (!recordingId) {
          chatStore.appendPushMessage(
            `⚠️ 无法找到技能「${skillKeyword}」的录制记录，回放失败。`,
          );
          antMessage.error("找不到录制记录");
          return;
        }
        const data = await browserApi.replayRecording({
          recordingId,
          profile: `${profileId || "default"}-replay`,
        });
        if (data.status === "passed") {
          antMessage.success(
            t("browser.recordReplay.replayPassed", "回放完成"),
          );
          chatStore.appendPushMessage(
            `🎬 Browser-Skill「${skillKeyword}」回放完成！`,
          );
        } else {
          const globalError = data.error || "";
          const failedSteps = (data.steps || [])
            .filter((s) => s.status === "failed")
            .map((s) => `步骤 ${s.id} (${s.kind}): ${s.error || "执行失败"}`);
          const detailMsg =
            globalError ||
            (failedSteps.length > 0 ? failedSteps.join("\n") : "") ||
            t("browser.recordReplay.replayFailed", "回放失败");
          antMessage.error(detailMsg);
          chatStore.appendPushMessage(
            `⚠️ 技能「${skillKeyword}」回放失败：\n${detailMsg}`,
          );
        }
      } catch (err) {
        antMessage.error(err instanceof Error ? err.message : "回放失败");
        chatStore.appendPushMessage(
          `⚠️ 技能回放出错：${err instanceof Error ? err.message : "未知错误"}`,
        );
      } finally {
        workflowBusyRef.current = false;
        setBrowserReplayBusy(false);
      }
    },
    [agentId, browserLastRecordingId, profileId, t],
  );

  const handleReplay = useCallback(async () => {
    if (!browserLastRecordingId || browserRecording || browserReplayBusy)
      return;
    setBrowserReplayBusy(true);
    try {
      const data = await browserApi.replayRecording({
        recordingId: browserLastRecordingId!,
        profile: `${profileId || "default"}-replay`,
      });
      if (data.status === "passed") {
        antMessage.success(t("browser.recordReplay.replayPassed", "回放完成"));
        chatStore.appendPushMessage("🔄 技能回放完成！所有步骤已成功执行。");
      } else {
        antMessage.error(
          data.error || t("browser.recordReplay.replayFailed", "回放失败"),
        );
        chatStore.appendPushMessage(
          `⚠️ 技能回放失败：${data.error || "未知错误"}`,
        );
      }
    } catch (err) {
      antMessage.error(err instanceof Error ? err.message : "回放失败");
    } finally {
      setBrowserReplayBusy(false);
    }
  }, [
    browserLastRecordingId,
    browserRecording,
    browserReplayBusy,
    profileId,
    t,
  ]);

  // --- Intercept user messages based on recording phase ---
  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming || !activeAgent) return;
    setInputValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    if (recordingPhase === "awaitObjective") {
      void handleObjectiveInput(text);
      return;
    }
    if (recordingPhase === "awaitDescription") {
      void handleDescriptionInput(text);
      return;
    }
    if (isEndRecordingCommand(text)) {
      void handleEndRecording();
      return;
    }
    if (isConfirmSkillCommand(text)) {
      void handleConfirmSkill();
      return;
    }
    if (isSkillTriggerCommand(text)) {
      chatStore.appendPushMessage(`🔄 正在使用技能「${text}」进行回放...`);
      void handleSkillReplay(text);
      return;
    }
    send(text);
  }, [
    activeAgent,
    inputValue,
    isStreaming,
    send,
    recordingPhase,
    isEndRecordingCommand,
    isConfirmSkillCommand,
    isSkillTriggerCommand,
    handleObjectiveInput,
    handleDescriptionInput,
    handleEndRecording,
    handleConfirmSkill,
    handleSkillReplay,
  ]);

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

  // When recording is active and agent stream just finished, append reminder
  const prevStreamingRef = useRef(false);
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current;
    prevStreamingRef.current = isStreaming;
    if (
      wasStreaming &&
      !isStreaming &&
      browserRecording &&
      recordingPhase === "recording" &&
      messages.length > 0 &&
      !workflowBusyRef.current
    ) {
      chatStore.appendPushMessage(
        '💡 录制还在进行中。如果操作已完成，输入"结束"即可停止录制并生成技能脚本。',
      );
    }
  }, [isStreaming, browserRecording, recordingPhase, messages.length]);

  const inputDisabled =
    isStreaming || booting || !threadId || browserReplayBusy;

  // Dynamic placeholder
  const placeholder = useMemo(() => {
    if (recordingPhase === "awaitObjective") {
      return t(
        "remoteBrowser.ai.objectivePlaceholder",
        "请输入任务目标（将作为技能名称和触发关键词）",
      );
    }
    if (recordingPhase === "awaitDescription") {
      return t(
        "remoteBrowser.ai.descriptionPlaceholder",
        "请描述你想让AI在浏览器中执行的操作...",
      );
    }
    if (browserRecording) {
      return t(
        "remoteBrowser.ai.recordingPlaceholder",
        '录制进行中...输入"结束"停止录制',
      );
    }
    if (pendingSkillContent) {
      return t(
        "remoteBrowser.ai.confirmPlaceholder",
        '输入"确认"应用技能，或继续对话',
      );
    }
    if (savedSkillNames.length > 0) {
      return t(
        "remoteBrowser.ai.placeholderWithSkills",
        `输入技能名触发回放，或继续对话`,
      );
    }
    return t(
      "remoteBrowser.ai.inputPlaceholder",
      "问问当前网页或让 AI 继续操作浏览器...",
    );
  }, [
    recordingPhase,
    browserRecording,
    pendingSkillContent,
    savedSkillNames,
    t,
  ]);

  // No agent → show empty state
  if (!activeAgent) {
    return (
      <div className={panelClassName}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <Bot size={14} />
            <span>{t("remoteBrowser.ai.title", "AI 助手")}</span>
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
            {t("remoteBrowser.ai.noAgentTitle", "请选择一个 Agent")}
          </div>
          <div className={styles.emptyDesc}>
            {t(
              "remoteBrowser.ai.noAgentDesc",
              "浏览器右侧助手会复用当前 Agent 的对话能力。",
            )}
          </div>
          <div className={styles.emptyAgentPicker}>
            <AgentSelector variant="select" showLabel={false} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={panelClassName}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>
          <Bot size={14} />
          <span>{t("remoteBrowser.ai.title", "AI 助手")}</span>
          {browserRecording && recordingPhase !== "idle" && (
            <Tag color="red" className={styles.recordingTag}>
              ● REC{" "}
              {skillName && recordingPhase === "recording"
                ? `— ${skillName}`
                : ""}
            </Tag>
          )}
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
            {t("remoteBrowser.ai.expert", "专家")}
          </span>
          <AgentSelector variant="select" showLabel={false} />
        </div>
        <div className={styles.contextGrid}>
          <span className={styles.contextLabel}>
            {t("remoteBrowser.ai.profile", "Profile")}
          </span>
          <span className={styles.contextValue}>{profileId || "default"}</span>
          <span className={styles.contextLabel}>
            {t("remoteBrowser.ai.currentUrl", "当前网页")}
          </span>
          <span
            className={styles.contextValue}
            title={currentUrl || activeTab?.url}
          >
            {currentUrl || activeTab?.url || "about:blank"}
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
        {/* Recording action buttons before the send row */}
        {browserRecording && recordingPhase === "recording" && (
          <Tooltip title={t("browser.recordReplay.stop", "停止浏览器录制")}>
            <button
              type="button"
              className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
              onClick={handleEndRecording}
            >
              <Square size={14} />
            </button>
          </Tooltip>
        )}
        {!browserRecording && browserLastRecordingId && !browserReplayBusy && (
          <Tooltip
            title={t("browser.recordReplay.replay", "回放最近一次浏览器录制")}
          >
            <button
              type="button"
              className={styles.actionBtn}
              disabled={isStreaming}
              onClick={handleReplay}
            >
              <Play size={14} />
            </button>
          </Tooltip>
        )}
        {browserReplayBusy && <Loader2 size={14} className={styles.spinIcon} />}
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
            placeholder={placeholder}
            rows={1}
            disabled={inputDisabled}
          />
          <button
            type="button"
            className={styles.sendBtn}
            disabled={!inputValue.trim() || inputDisabled}
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
