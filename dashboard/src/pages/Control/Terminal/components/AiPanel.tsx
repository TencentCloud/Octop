import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import cx from "classnames";
import { Button, Input, Spin, Segmented } from "antd";
import { SquareTerminal, Send, Square } from "lucide-react";
import AssistantFrame, {
  type AssistantPlacement,
} from "../../../../components/AssistantFrame/AssistantFrame";
import type { OctopAgent } from "../../../../context/AgentContext";
import { terminalAiApi } from "../../../../api/modules/terminalAi";
import { providerApi } from "../../../../api/modules/provider";
import {
  apiErrorMessage,
  isNotFoundApiError,
} from "../../../../utils/apiError";
import { isAgentModelConfigError } from "../../../../utils/agentError";
import { formatOpsEnsureError } from "../useOpsEngineer";
import type { TerminalContext } from "../../../../api/modules/terminalAi";
import { useAgentThreadChat } from "../../../../hooks/useAgentThreadChat";
import { useTerminalAutopilot } from "../../../../hooks/useTerminalAutopilot";
import MessageList from "../../../Chat/components/MessageList";
import chatStyles from "../../../Chat/index.module.less";
import { formatTerminalUserMessage } from "../terminalContext";
import AutopilotPlan from "./AutopilotPlan";
import styles from "./AiPanel.module.less";

export type AiPanelMode = "assist" | "autopilot";

export interface AiPanelProps {
  /** 运维工程师。终端进程和这段对话都用它。 */
  agent: OctopAgent | null;
  ensuring?: boolean;
  ensureError?: string | null;
  onEnsureRetry?: () => void;
  activeTerminalSessionId: string | null;
  activeTerminalSessionIndex: number;
  placement: AssistantPlacement;
  /** 窄屏锁定在底部，不提供浮动和侧栏切换。 */
  placementLocked?: boolean;
  /** 终端提供底部、右侧和取消停靠。 */
  placements?: readonly AssistantPlacement[];
  onPlacementChange: (placement: AssistantPlacement) => void;
  /** 工作台切走时收起窗口，会话仍留在这个面板里。 */
  hidden?: boolean;
  onClose: () => void;
  onExecuteCommand: (cmd: string) => void;
  getRecentTerminalOutput: () => string;
  snapshotTerminalOutput: () => string;
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
  variant,
  onRetry,
  creating,
  error,
}: {
  variant: "create" | "model";
  onRetry?: () => void;
  creating?: boolean;
  error?: string | null;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const missingModel = variant === "model";

  return (
    <div className={styles.gate}>
      <SquareTerminal size={32} color="var(--fn-text-quaternary, #9ca3af)" />
      <div className={styles.gateTitle}>
        {missingModel
          ? t("terminal.ai.gateNoProvider")
          : t("terminal.ai.gateTitle")}
      </div>
      {missingModel ? null : (
        <div className={styles.gateDesc}>{t("terminal.ai.gateDesc")}</div>
      )}
      {missingModel ? (
        <Button type="primary" onClick={() => navigate("/admin/models")}>
          {t("terminal.ai.gateConfigureLink")}
        </Button>
      ) : (
        <Button type="primary" loading={creating} onClick={() => onRetry?.()}>
          {creating
            ? t("terminal.ai.gateCreating")
            : t("terminal.ai.gateCreate")}
        </Button>
      )}
      {!missingModel && error ? (
        <div className={styles.gateError}>{error}</div>
      ) : null}
    </div>
  );
}

export default function AiPanel({
  agent,
  ensuring = false,
  ensureError = null,
  onEnsureRetry,
  activeTerminalSessionId,
  activeTerminalSessionIndex,
  placement,
  placementLocked = false,
  placements,
  onPlacementChange,
  hidden = false,
  onClose,
  onExecuteCommand,
  getRecentTerminalOutput,
  snapshotTerminalOutput,
}: AiPanelProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<AiPanelMode>("assist");
  const [inputValue, setInputValue] = useState("");
  const [terminalCtx, setTerminalCtx] = useState<TerminalContext | null>(null);
  const [needsModel, setNeedsModel] = useState(false);
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
    send,
    cancelStream,
  } = useAgentThreadChat(agent?.agent_id ?? null, {
    // v2 was saved while this panel still followed the sidebar expert, so it
    // reopened that expert's conversation. This pin belongs only to ops-engineer.
    pinKey: "octop:terminal-ai-thread:ops-engineer:v1",
  });
  const modelBlocked = needsModel || isAgentModelConfigError(bootError);

  useEffect(() => {
    if (!agent) {
      setTerminalCtx(null);
      return;
    }
    let cancelled = false;
    terminalAiApi
      .getContext(agent.agent_id)
      .then((data) => {
        if (!cancelled) setTerminalCtx(data);
      })
      .catch(() => {
        if (!cancelled) setTerminalCtx(null);
      });
    return () => {
      cancelled = true;
    };
  }, [agent?.agent_id]);

  useEffect(() => {
    if (!agent) {
      setNeedsModel(false);
      return;
    }
    const hasOwnModel = Boolean(agent.default_model?.trim());
    if (hasOwnModel && !isAgentModelConfigError(agent.last_error)) {
      setNeedsModel(false);
      return;
    }
    if (isAgentModelConfigError(agent.last_error)) {
      setNeedsModel(true);
      return;
    }
    let cancelled = false;
    void providerApi
      .getActiveModel()
      .then((active) => {
        if (cancelled) return;
        const provider = (active.provider_name || "").trim();
        const model = (active.model || "").trim();
        setNeedsModel(!provider || !model);
      })
      .catch((err: unknown) => {
        if (!cancelled) setNeedsModel(isNotFoundApiError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [agent]);

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
    if (!text || isStreaming || !agent || autopilot.isActive) return;
    setInputValue("");
    send(formatMessage(text));
  }, [inputValue, isStreaming, agent, autopilot.isActive, send, formatMessage]);

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

  const inputDisabled =
    isStreaming || booting || !threadId || autopilot.isActive;
  const activeInputValue = mode === "autopilot" ? autopilot.goal : inputValue;

  return (
    <AssistantFrame
      placement={placement}
      onPlacementChange={onPlacementChange}
      placementKey="octop:terminal-ai-layout-v2"
      storageKey="octop:terminal-ai"
      legacySize={{
        widthKey: "octop:terminal-ai-width",
        heightKey: "octop:terminal-ai-height",
      }}
      dock="inline"
      defaultDockWidth={400}
      placementLocked={placementLocked}
      placements={placements}
      hidden={hidden}
      title={t("terminal.ai.togglePanel")}
      onClose={onClose}
      headerExtra={
        agent && !modelBlocked ? (
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
        ) : null
      }
    >
      <div className={styles.panel}>
        {agent && <ContextSection ctx={terminalCtx} />}

        {!agent ? (
          ensureError ? (
            <GateView
              variant="create"
              onRetry={onEnsureRetry}
              creating={ensuring}
              error={formatOpsEnsureError(ensureError, t)}
            />
          ) : (
            <div className={styles.messagesLoading}>
              <Spin size="small" />
            </div>
          )
        ) : modelBlocked ? (
          <GateView variant="model" />
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

            <div className={cx(styles.messages, chatStyles.messageListWrapper)}>
              {booting ? (
                <div className={styles.messagesLoading}>
                  <Spin size="small" />
                </div>
              ) : bootError ? (
                <div className={styles.messagesError}>
                  {apiErrorMessage(new Error(bootError), bootError, t)}
                </div>
              ) : (
                <MessageList
                  messages={messages}
                  isStreaming={isStreaming}
                  sessionKey={threadId ?? undefined}
                  onRunShellCommand={handleRunShellCommand}
                  shellCommandDisabled={shellDisabled}
                  shellCommandDisabledTitle={shellDisabledTitle}
                  compactProcess
                />
              )}
            </div>

            {!activeTerminalSessionId ? (
              <div className={styles.composer}>
                <span className={styles.hint}>
                  {t("terminal.ai.noTerminal")}
                </span>
              </div>
            ) : (
              <div className={styles.composer}>
                <Input.TextArea
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  value={activeInputValue}
                  disabled={booting || !threadId || autopilot.isActive}
                  placeholder={
                    mode === "autopilot"
                      ? t("terminal.ai.autopilotGoalPlaceholder")
                      : t("terminal.ai.inputPlaceholder")
                  }
                  onChange={(event) => {
                    if (mode === "autopilot") {
                      autopilot.setGoal(event.target.value);
                    } else {
                      setInputValue(event.target.value);
                    }
                  }}
                  onCompositionStart={() => {
                    imeComposingRef.current = true;
                  }}
                  onCompositionEnd={() => {
                    imeComposingRef.current = false;
                  }}
                  onPressEnter={handleKeyDown}
                />
                <div className={styles.composerActions}>
                  <span className={styles.hint}>{t("chat.composerHint")}</span>
                  {mode === "assist" ? (
                    isStreaming ? (
                      <Button
                        size="small"
                        danger
                        icon={<Square size={13} />}
                        disabled={booting || !threadId}
                        onClick={cancelStream}
                      >
                        {t("chat.stop")}
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        type="primary"
                        icon={<Send size={13} />}
                        disabled={!inputValue.trim() || inputDisabled}
                        onClick={handleSend}
                      >
                        {t("chat.send")}
                      </Button>
                    )
                  ) : null}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AssistantFrame>
  );
}
