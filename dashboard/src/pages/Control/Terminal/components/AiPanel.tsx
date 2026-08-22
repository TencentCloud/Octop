import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { useTranslation } from "react-i18next";
import { Button, Tooltip, Spin, Segmented } from "antd";
import { X, PanelRight, PanelBottom, SquareTerminal, Send } from "lucide-react";
import type { OctopAgent } from "../../../../context/AgentContext";
import { terminalAiApi } from "../../../../api/modules/terminalAi";
import type { TerminalContext } from "../../../../api/modules/terminalAi";
import { useAgentThreadChat } from "../../../../hooks/useAgentThreadChat";
import { useTerminalAutopilot } from "../../../../hooks/useTerminalAutopilot";
import MessageList from "../../../Chat/components/MessageList";
import chatStyles from "../../../Chat/index.module.less";
import { formatTerminalUserMessage } from "../terminalContext";
import AutopilotPlan from "./AutopilotPlan";
import styles from "./AiPanel.module.less";

export type AiPanelLayout = "right" | "bottom";
export type AiPanelMode = "assist" | "autopilot";

export interface AiPanelProps {
  activeAgent: OctopAgent | null;
  agents: OctopAgent[];
  activeTerminalSessionId: string | null;
  activeTerminalSessionIndex: number;
  layout: AiPanelLayout;
  /** When false, hide the right/bottom layout toggle (e.g. mobile forces bottom). */
  layoutSwitchable?: boolean;
  onLayoutChange: (layout: AiPanelLayout) => void;
  onClose: () => void;
  onExecuteCommand: (cmd: string) => void;
  getRecentTerminalOutput: () => string;
  snapshotTerminalOutput: () => string;
  onAgentCreated: () => void;
}

function findOpsEngineer(agents: OctopAgent[]): OctopAgent | null {
  return (
    agents.find((a) => {
      if (a.template_name === "ops-engineer") return true;
      const cfg = a.config ?? {};
      if (cfg.expert_id === "ops-engineer") return true;
      const name = a.name.toLowerCase();
      return (
        name.includes("ops") ||
        name.includes("engineer") ||
        name.includes("运维")
      );
    }) ?? null
  );
}

function ContextSection({ ctx }: { ctx: TerminalContext | null }) {
  const { t } = useTranslation();

  if (!ctx) {
    return (
      <div className={styles.contextSection}>
        <span className={styles.contextEmpty}>
          {t("terminal.ai.contextEmpty")}
        </span>
      </div>
    );
  }

  const rows: Array<[string, string]> = [
    [t("terminal.ai.contextOs"), ctx.distro || ctx.os],
    [t("terminal.ai.contextShell"), ctx.shell],
    [t("terminal.ai.contextHostname"), ctx.hostname],
    [t("terminal.ai.contextUser"), ctx.username],
    [t("terminal.ai.contextCwd"), ctx.workspace_dir],
  ];

  return (
    <div className={styles.contextSection}>
      <div className={styles.contextGrid}>
        {rows.map(([label, value]) => (
          <React.Fragment key={label}>
            <span className={styles.contextLabel}>{label}</span>
            <span className={styles.contextValue} title={value}>
              {value}
            </span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function GateView({
  onCreated,
}: {
  onCreated: (agent: { agent_id: string; name: string }) => void;
}) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);

  const handleCreate = useCallback(async () => {
    setCreating(true);
    try {
      const result = await terminalAiApi.createOpsEngineer();
      onCreated({ agent_id: result.agent_id, name: result.name });
    } catch {
      // ignore — user can retry
    } finally {
      setCreating(false);
    }
  }, [onCreated]);

  return (
    <div className={styles.gate}>
      <SquareTerminal size={32} color="var(--fn-text-quaternary, #9ca3af)" />
      <div className={styles.gateTitle}>{t("terminal.ai.gateTitle")}</div>
      <div className={styles.gateDesc}>{t("terminal.ai.gateDesc")}</div>
      <Button
        type="primary"
        loading={creating}
        onClick={() => void handleCreate()}
      >
        {creating ? t("terminal.ai.gateCreating") : t("terminal.ai.gateCreate")}
      </Button>
    </div>
  );
}

export default function AiPanel({
  activeAgent,
  agents,
  activeTerminalSessionId,
  activeTerminalSessionIndex,
  layout,
  layoutSwitchable = true,
  onLayoutChange,
  onClose,
  onExecuteCommand,
  getRecentTerminalOutput,
  snapshotTerminalOutput,
  onAgentCreated,
}: AiPanelProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<AiPanelMode>("assist");
  const [inputValue, setInputValue] = useState("");
  const [terminalCtx, setTerminalCtx] = useState<TerminalContext | null>(null);
  const [opsAgent, setOpsAgent] = useState<OctopAgent | null>(() =>
    findOpsEngineer(agents),
  );
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imeComposingRef = useRef(false);
  /** Terminal context is injected only on the first outbound message per thread. */
  const contextInjectedRef = useRef(false);

  const contextLabels = useMemo(
    () => ({
      os: t("terminal.ai.contextOs"),
      shell: t("terminal.ai.contextShell"),
      hostname: t("terminal.ai.contextHostname"),
      user: t("terminal.ai.contextUser"),
      cwd: t("terminal.ai.contextCwd"),
    }),
    [t],
  );

  const {
    threadId,
    booting,
    bootError,
    messages,
    isStreaming,
    taskPlan,
    send,
    cancelStream,
  } = useAgentThreadChat(opsAgent?.agent_id ?? null);

  useEffect(() => {
    setOpsAgent(findOpsEngineer(agents));
  }, [agents]);

  useEffect(() => {
    if (!activeAgent) {
      setTerminalCtx(null);
      return;
    }
    let cancelled = false;
    terminalAiApi
      .getContext(activeAgent.agent_id)
      .then((data) => {
        if (!cancelled) setTerminalCtx(data);
      })
      .catch(() => {
        if (!cancelled) setTerminalCtx(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch only when agent id changes
  }, [activeAgent?.agent_id]);

  useEffect(() => {
    if (!threadId) {
      contextInjectedRef.current = false;
      return;
    }
    contextInjectedRef.current = messages.some((m) => m.role === "user");
  }, [threadId, messages]);

  const formatMessage = useCallback(
    (userText: string, autopilot?: boolean) => {
      const includeContext =
        !contextInjectedRef.current && terminalCtx !== null;
      if (includeContext) {
        contextInjectedRef.current = true;
      }
      return formatTerminalUserMessage(terminalCtx, userText, contextLabels, {
        autopilot: autopilot || undefined,
        includeContext,
      });
    },
    [terminalCtx, contextLabels],
  );

  const autopilot = useTerminalAutopilot({
    send,
    messages,
    isStreaming,
    onExecuteCommand,
    activeTerminalSessionId,
    formatMessage,
    getRecentOutput: getRecentTerminalOutput,
    snapshotOutput: snapshotTerminalOutput,
  });

  const handleGateCreated = useCallback(
    (created: { agent_id: string; name: string }) => {
      setOpsAgent({
        id: 0,
        agent_id: created.agent_id,
        name: created.name,
        description: null,
        persona_mbti: null,
        default_model: null,
        system_prompt: null,
        template_name: "ops-engineer",
        state: "stopped",
        last_error: null,
        icon: null,
        icon_name: "terminal",
        icon_url: null,
        color: null,
        config: { expert_id: "ops-engineer" },
      });
      onAgentCreated();
    },
    [onAgentCreated],
  );

  const shellDisabled = !activeTerminalSessionId;
  const shellDisabledTitle = t("terminal.ai.noTerminal");

  const handleRunShellCommand = useCallback(
    (code: string) => {
      if (!activeTerminalSessionId) return;
      onExecuteCommand(code);
    },
    [activeTerminalSessionId, onExecuteCommand],
  );

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || isStreaming || !opsAgent || autopilot.isActive) return;
    setInputValue("");
    send(formatMessage(text));
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [
    inputValue,
    isStreaming,
    opsAgent,
    autopilot.isActive,
    send,
    formatMessage,
  ]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      // IME composition: Enter confirms the candidate, not send.
      if (
        imeComposingRef.current ||
        e.nativeEvent.isComposing ||
        e.keyCode === 229
      ) {
        return;
      }
      e.preventDefault();
      if (mode === "assist") handleSend();
    },
    [handleSend, mode],
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

  const inputDisabled =
    isStreaming || booting || !threadId || autopilot.isActive;
  const activeInputValue = mode === "autopilot" ? autopilot.goal : inputValue;

  const panelClass = `${styles.panel}${
    layout === "bottom" ? ` ${styles.panelBottom}` : ""
  }`;

  return (
    <div className={panelClass}>
      <div className={styles.header}>
        <span className={styles.headerTitle}>
          {t("terminal.ai.togglePanel")}
        </span>
        <div className={styles.headerActions}>
          {opsAgent && (
            <Segmented
              size="small"
              className={styles.modeSegmented}
              value={mode}
              onChange={(v) => setMode(v as AiPanelMode)}
              options={[
                { label: t("terminal.ai.modeAssist"), value: "assist" },
                { label: t("terminal.ai.modeAutopilot"), value: "autopilot" },
              ]}
              disabled={autopilot.isActive}
            />
          )}
          {layoutSwitchable && (
            <Tooltip
              title={
                layout === "right"
                  ? t("terminal.ai.layoutBottom")
                  : t("terminal.ai.layoutRight")
              }
            >
              <Button
                type="text"
                size="small"
                icon={
                  layout === "right" ? (
                    <PanelBottom size={14} />
                  ) : (
                    <PanelRight size={14} />
                  )
                }
                onClick={() =>
                  onLayoutChange(layout === "right" ? "bottom" : "right")
                }
              />
            </Tooltip>
          )}
          <Button
            type="text"
            size="small"
            icon={<X size={14} />}
            onClick={onClose}
          />
        </div>
      </div>

      {activeAgent && <ContextSection ctx={terminalCtx} />}

      {!opsAgent ? (
        <GateView onCreated={handleGateCreated} />
      ) : (
        <>
          {activeTerminalSessionId && (
            <div className={styles.sessionTarget}>
              {t("terminal.ai.sendTo", {
                session: `${t(
                  "terminal.session",
                )} ${activeTerminalSessionIndex}`,
              })}
            </div>
          )}

          {mode === "autopilot" && (
            <AutopilotPlan
              status={autopilot.status}
              steps={autopilot.steps}
              currentIndex={autopilot.currentIndex}
              onStart={autopilot.startPlanning}
              onPause={autopilot.pause}
              onResume={autopilot.resume}
              onStop={autopilot.stop}
              onRetry={autopilot.retryStep}
              onSkip={autopilot.skipStep}
              canStart={
                !!autopilot.goal.trim() &&
                !!activeTerminalSessionId &&
                !isStreaming &&
                !booting &&
                !!threadId &&
                !autopilot.isActive
              }
            />
          )}

          <div
            className={`${styles.messages} ${chatStyles.messageListWrapper}`}
          >
            {booting ? (
              <div className={styles.messagesLoading}>
                <Spin size="small" />
              </div>
            ) : bootError ? (
              <div className={styles.messagesError}>{bootError}</div>
            ) : (
              <MessageList
                messages={messages}
                taskPlan={taskPlan}
                isStreaming={isStreaming}
                sessionKey={threadId ?? undefined}
                onCancel={cancelStream}
                onRunShellCommand={handleRunShellCommand}
                shellCommandDisabled={shellDisabled}
                shellCommandDisabledTitle={shellDisabledTitle}
                compactProcess
              />
            )}
          </div>

          {!activeTerminalSessionId ? (
            <div className={styles.sendBar}>
              <span className={styles.sendBarHint}>
                {t("terminal.ai.noTerminal")}
              </span>
            </div>
          ) : (
            <div className={styles.sendBar}>
              <div className={styles.sendRow}>
                <textarea
                  ref={textareaRef}
                  className={styles.sendTextarea}
                  value={activeInputValue}
                  onCompositionStart={() => {
                    imeComposingRef.current = true;
                  }}
                  onCompositionEnd={() => {
                    imeComposingRef.current = false;
                  }}
                  onChange={(e) => {
                    if (mode === "autopilot") {
                      autopilot.setGoal(e.target.value);
                    } else {
                      handleTextareaInput(e);
                    }
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    mode === "autopilot"
                      ? t("terminal.ai.autopilotGoalPlaceholder")
                      : t("terminal.ai.inputPlaceholder")
                  }
                  rows={1}
                  disabled={inputDisabled}
                />
                {mode === "assist" ? (
                  <button
                    type="button"
                    className={styles.sendBtn}
                    disabled={!inputValue.trim() || inputDisabled}
                    onClick={handleSend}
                    title={t("terminal.ai.send")}
                  >
                    <Send size={16} />
                  </button>
                ) : null}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
