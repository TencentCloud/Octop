// dashboard/src/pages/Experts/components/AgentCard.tsx
import { memo, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Popconfirm, Switch, Tooltip, message } from "antd";
import {
  Copy,
  Pencil,
  Trash2,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  FolderOpen,
  MessageSquare,
  Bot,
  Sparkles,
} from "lucide-react";
import WorkspaceDrawer from "../../Agent/Workspace/components/WorkspaceDrawer";
import SubagentCatalogDrawer from "./SubagentCatalogDrawer";
import SkillCatalogDrawer from "./SkillCatalogDrawer";
import MbtiCatalogDrawer from "./MbtiCatalogDrawer";
import { request } from "../../../api/request";
import type { OctopAgent } from "../../../context/AgentContext";
import { useAgent } from "../../../context/AgentContext";
import MbtiPersonaTag from "../../../components/MbtiPersonaTag";
import { iconForName } from "./iconForName";
import {
  formatAgentError,
  formatAgentState,
  isAgentChatReady,
  isAgentModelConfigError,
} from "../../../utils/agentError";
import styles from "../index.module.less";

const STATE_META: Record<
  string,
  { color: string; bg: string; spin?: boolean }
> = {
  running: { color: "#52c41a", bg: "rgba(82,196,26,0.12)" },
  stopped: { color: "#8c8c8c", bg: "rgba(140,140,140,0.10)" },
  created: { color: "#8c8c8c", bg: "rgba(140,140,140,0.10)" },
  failed: { color: "#ff4d4f", bg: "rgba(255,77,79,0.10)" },
  starting: { color: "#1677ff", bg: "rgba(22,119,255,0.10)", spin: true },
  stopping: { color: "#1677ff", bg: "rgba(22,119,255,0.10)", spin: true },
};

function getStateMeta(state: string) {
  return STATE_META[state] ?? STATE_META.stopped;
}

const TRANSIENT = new Set(["starting", "stopping"]);

export interface AgentCardProps {
  agent: OctopAgent;
  iconName?: string | null;
  accentColor?: string | null;
  onEdit: (agentId: string) => void;
  onDeleted: (agentId: string) => void;
  onStateChange: (agentId: string, newState: string) => void;
  /** Called when a start/stop poll settles (e.g. admin views another user's agents). */
  onPollSettled?: () => void;
}

export const AgentCard = memo(function AgentCard({
  agent,
  iconName,
  accentColor,
  onEdit,
  onDeleted,
  onStateChange,
  onPollSettled,
}: AgentCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setActiveAgent, refresh: refreshAgents } = useAgent();

  const [localState, setLocalState] = useState(agent.state);
  const [localError, setLocalError] = useState(agent.last_error);
  const [actionLoading, setActionLoading] = useState(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);
  const [subagentCatalogOpen, setSubagentCatalogOpen] = useState(false);
  const [skillCatalogOpen, setSkillCatalogOpen] = useState(false);
  const [mbtiCatalogOpen, setMbtiCatalogOpen] = useState(false);
  const [installedSubagentSlugs, setInstalledSubagentSlugs] = useState<
    Set<string>
  >(() => new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setLocalState(agent.state);
    setLocalError(agent.last_error);
  }, [agent.state, agent.last_error]);

  // Poll during transient states
  useEffect(() => {
    if (!TRANSIENT.has(localState)) {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
      return;
    }
    pollRef.current = setInterval(() => {
      request<{ state: string; last_error: string | null }>(
        `/agents/${agent.agent_id}/status`,
      )
        .then((s) => {
          setLocalState(s.state);
          setLocalError(s.last_error);
          onStateChange(agent.agent_id, s.state);
          if (!TRANSIENT.has(s.state)) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            onPollSettled?.();
            void refreshAgents({ silent: true });
          }
        })
        .catch(() => {});
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [localState, agent.agent_id, onStateChange, onPollSettled, refreshAgents]);

  const isTransient = TRANSIENT.has(localState);
  const switchChecked = localState === "running" || localState === "starting";

  const handleToggle = useCallback(
    async (checked: boolean) => {
      setActionLoading(true);
      try {
        if (checked) {
          await request(`/agents/${agent.agent_id}/start`, { method: "POST" });
          setLocalState("starting");
          onStateChange(agent.agent_id, "starting");
          message.success(t("experts.agentStarted", { name: agent.name }));
        } else {
          await request(`/agents/${agent.agent_id}/stop`, { method: "POST" });
          setLocalState("stopping");
          onStateChange(agent.agent_id, "stopping");
          message.success(t("experts.agentStopped", { name: agent.name }));
        }
      } catch {
        message.error(
          checked
            ? t("experts.agentStartFailed")
            : t("experts.agentStopFailed"),
        );
      } finally {
        setActionLoading(false);
      }
    },
    [agent.agent_id, agent.name, t, onStateChange],
  );

  const handleDelete = useCallback(async () => {
    try {
      await request(`/agents/${agent.agent_id}`, { method: "DELETE" });
      message.success(t("experts.agentDeleted", { name: agent.name }));
      onDeleted(agent.agent_id);
    } catch {
      message.error(t("experts.agentDeleteFailed"));
    }
  }, [agent.agent_id, agent.name, t, onDeleted]);

  const handleReload = useCallback(async () => {
    setActionLoading(true);
    try {
      await request(`/agents/${agent.agent_id}/reload`, { method: "POST" });
      message.success(t("experts.agentReloadSuccess", { name: agent.name }));
    } catch {
      message.error(t("experts.agentReloadFailed"));
    } finally {
      setActionLoading(false);
    }
  }, [agent.agent_id, agent.name, t]);

  const handleOpenChat = useCallback(() => {
    setActiveAgent(agent.agent_id);
    navigate("/chat");
  }, [agent.agent_id, setActiveAgent, navigate]);

  const copyAgentId = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(agent.agent_id);
      message.success(t("common.copied"));
    } catch {
      message.error(t("common.copyFailed"));
    }
  }, [agent.agent_id, t]);

  const reloadInstalledSubagents = useCallback(async () => {
    if (!isAgentChatReady(localState)) {
      setInstalledSubagentSlugs(new Set());
      return;
    }
    try {
      const rows = await request<{ slug: string }[]>(
        `/agents/${agent.agent_id}/subagents`,
      );
      setInstalledSubagentSlugs(new Set(rows.map((r) => r.slug)));
    } catch {
      setInstalledSubagentSlugs(new Set());
    }
  }, [agent.agent_id, localState]);

  const openSubagentCatalog = useCallback(() => {
    setSubagentCatalogOpen(true);
    void reloadInstalledSubagents();
  }, [reloadInstalledSubagents]);

  const accent = accentColor || "#6366f1";
  const meta = getStateMeta(localState);
  const friendlyError = formatAgentError(localError, t);
  const chatReady = isAgentChatReady(localState);

  return (
    <>
      <div
        className={styles.agentCard2}
        style={{ "--agent-accent": accent } as React.CSSProperties}
      >
        {/* Accent top bar */}
        <div className={styles.agentCard2Accent} />

        {/* Header */}
        <div className={styles.agentCard2Header}>
          <div
            className={styles.agentCard2Icon}
            style={{ color: accent, background: `${accent}1a` }}
          >
            {iconForName(iconName, 22)}
          </div>

          <div className={styles.agentCard2TitleBlock}>
            <div className={styles.agentCard2Name}>{agent.name}</div>
            <Tooltip title={t("experts.copyAgentId")}>
              <button
                type="button"
                className={styles.agentCardId}
                onClick={() => void copyAgentId()}
              >
                <span className={styles.agentCardIdLabel}>
                  {t("experts.agentId")}
                </span>
                <span className={styles.agentCardIdValue}>
                  {agent.agent_id}
                </span>
                <Copy size={11} className={styles.agentCardIdIcon} />
              </button>
            </Tooltip>
            <div className={styles.agentCard2Meta}>
              <div
                className={styles.agentCard2State}
                style={{ color: meta.color, background: meta.bg }}
              >
                <span
                  className={meta.spin ? styles.stateDotSpin : styles.stateDot2}
                  style={!meta.spin ? { background: meta.color } : undefined}
                />
                {formatAgentState(localState, t)}
              </div>
              <MbtiPersonaTag
                value={agent.persona_mbti}
                onClick={() => setMbtiCatalogOpen(true)}
              />
            </div>
          </div>

          <div className={styles.agentCard2HeaderActions}>
            <Tooltip title={t("experts.reloadAgent")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.agentCard2EditBtn}
                disabled={isTransient || actionLoading}
                onClick={() => void handleReload()}
                aria-label={t("experts.reloadAgent")}
              >
                <RefreshCw size={13} />
              </button>
            </Tooltip>

            <Switch
              size="small"
              checked={switchChecked}
              loading={isTransient || actionLoading}
              onChange={(checked) => void handleToggle(checked)}
              className={styles.agentCard2Switch}
            />
          </div>
        </div>

        {/* Description */}
        <p className={styles.agentCard2Desc}>{agent.description || "\u00a0"}</p>

        {/* Error */}
        {localState === "failed" && friendlyError && (
          <div className={styles.agentCardErrorWrap}>
            <Tooltip
              title={friendlyError}
              mouseEnterDelay={0.3}
              overlayStyle={{ maxWidth: 360 }}
            >
              <div className={styles.agentCardError}>
                <AlertCircle size={13} className={styles.agentCardErrorIcon} />
                <span className={styles.agentCardErrorText}>
                  {friendlyError}
                </span>
              </div>
            </Tooltip>
            {isAgentModelConfigError(localError) && (
              <button
                type="button"
                className={styles.agentCardErrorAction}
                onClick={() => navigate("/admin/models")}
              >
                {t("modelConfig.configureButton")}
              </button>
            )}
          </div>
        )}

        {/* Footer actions */}
        <div className={styles.agentCard2Footer}>
          <Tooltip title={t("pageShell.workspace.title")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.agentCard2EditBtn}
              onClick={() => setWorkspaceDrawerOpen(true)}
              aria-label={t("pageShell.workspace.title")}
            >
              <FolderOpen size={13} />
            </button>
          </Tooltip>

          <Tooltip title={t("experts.skillsBtn")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.agentCard2EditBtn}
              onClick={() => setSkillCatalogOpen(true)}
              aria-label={t("experts.skillsBtn")}
            >
              <Sparkles size={13} />
            </button>
          </Tooltip>

          <Tooltip title={t("experts.subagentsBtn")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.agentCard2EditBtn}
              onClick={openSubagentCatalog}
              aria-label={t("experts.subagentsBtn")}
            >
              <Bot size={13} />
            </button>
          </Tooltip>

          <Tooltip title={t("common.edit", "Edit")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.agentCard2EditBtn}
              onClick={() => onEdit(agent.agent_id)}
              aria-label={t("common.edit", "Edit")}
            >
              <Pencil size={13} />
            </button>
          </Tooltip>

          <Popconfirm
            title={t("experts.confirmDelete", { name: agent.name })}
            description={t("experts.confirmDeleteHint")}
            onConfirm={() => void handleDelete()}
            okText={t("common.delete", "Delete")}
            cancelText={t("common.cancel")}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={t("common.delete", "Delete")} mouseEnterDelay={0.5}>
              <button className={styles.agentCard2DelBtn}>
                <Trash2 size={13} />
              </button>
            </Tooltip>
          </Popconfirm>

          {chatReady ? (
            <button
              className={styles.agentCard2ChatBtn}
              style={{ color: accent, borderColor: `${accent}55` }}
              onClick={handleOpenChat}
            >
              <MessageSquare size={13} />
              {t("experts.openChat", "对话")}
              <ChevronRight size={13} />
            </button>
          ) : localState === "failed" ||
            localState === "stopped" ||
            localState === "created" ? (
            <button
              type="button"
              className={styles.agentCard2ChatBtn}
              style={{ color: accent, borderColor: `${accent}55` }}
              disabled={isTransient || actionLoading}
              onClick={() => void handleToggle(true)}
            >
              {localState === "failed"
                ? t("experts.retryStart", "重试启动")
                : t("experts.startAgent", "启动")}
            </button>
          ) : null}
        </div>
      </div>
      <WorkspaceDrawer
        agentId={agent.agent_id}
        open={workspaceDrawerOpen}
        onClose={() => setWorkspaceDrawerOpen(false)}
      />
      <SubagentCatalogDrawer
        agentId={agent.agent_id}
        agentState={localState}
        open={subagentCatalogOpen}
        installedSlugs={installedSubagentSlugs}
        onClose={() => setSubagentCatalogOpen(false)}
        onInstalled={() => {
          void reloadInstalledSubagents();
        }}
      />
      <SkillCatalogDrawer
        agentId={agent.agent_id}
        open={skillCatalogOpen}
        onClose={() => setSkillCatalogOpen(false)}
      />
      <MbtiCatalogDrawer
        open={mbtiCatalogOpen}
        agentId={agent.agent_id}
        onClose={() => setMbtiCatalogOpen(false)}
        onApplied={() => {
          setMbtiCatalogOpen(false);
          void refreshAgents({ silent: true, force: true });
        }}
      />
    </>
  );
});
