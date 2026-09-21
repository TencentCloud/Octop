import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Dropdown, Popconfirm, Switch, Tooltip } from "antd";
import type { MenuProps } from "antd";
import { message } from "@/utils/antdMessage";

import {
  AlertCircle,
  ChevronRight,
  FolderOpen,
  MessageSquare,
  MoreHorizontal,
  Notebook,
  Pencil,
  RefreshCw,
  Trash2,
  Users,
  Waypoints,
} from "lucide-react";
import WorkspaceDrawer from "../../Agent/Workspace/components/WorkspaceDrawer";
import ChannelCatalogDrawer from "./ChannelCatalogDrawer";
import MemoryCatalogDrawer from "./MemoryCatalogDrawer";
import { teamsApi } from "../../../api/modules/teams";
import { request } from "../../../api/request";
import type { OctopAgent } from "../../../context/AgentContext";
import { useAgent } from "../../../context/AgentContext";
import { ExpertIcon } from "./iconForName";
import {
  formatAgentError,
  formatAgentState,
  isAgentChatReady,
  isAgentModelConfigError,
} from "../../../utils/agentError";
import { TEAM_ICON_NAME, teamPortraitUrl } from "../../../utils/teamAgent";
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
const MAX_VISIBLE_MEMBERS = 6;

export interface TeamCardProps {
  agent: OctopAgent;
  experts: OctopAgent[];
  onEdit: (agentId: string) => void;
  onDeleted: (agentId: string) => void;
  onStateChange: (agentId: string, newState: string) => void;
}

interface MemberChip {
  id: string;
  name: string;
  color: string;
  iconName?: string | null;
  iconUrl?: string | null;
}

function resolveMembers(
  memberIds: string[] | undefined,
  experts: OctopAgent[],
): MemberChip[] {
  const byId = new Map(experts.map((item) => [item.agent_id, item]));
  const chips: MemberChip[] = [];
  for (const id of memberIds ?? []) {
    const expert = byId.get(id);
    if (!expert) continue;
    chips.push({
      id,
      name: expert.name,
      color: expert.color || "#0d9488",
      iconName: expert.icon_name,
      iconUrl: expert.icon_url,
    });
  }
  return chips;
}

export const TeamCard = memo(function TeamCard({
  agent,
  experts,
  onEdit,
  onDeleted,
  onStateChange,
}: TeamCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setActiveAgent, refresh: refreshAgents } = useAgent();

  const [localState, setLocalState] = useState(agent.state);
  const [localError, setLocalError] = useState(agent.last_error);
  const [actionLoading, setActionLoading] = useState(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);
  const [channelCatalogOpen, setChannelCatalogOpen] = useState(false);
  const [memoryCatalogOpen, setMemoryCatalogOpen] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const members = useMemo(
    () => resolveMembers(agent.member_ids, experts),
    [agent.member_ids, experts],
  );
  const visibleMembers = members.slice(0, MAX_VISIBLE_MEMBERS);
  const hiddenCount = Math.max(0, members.length - visibleMembers.length);

  useEffect(() => {
    setLocalState(agent.state);
    setLocalError(agent.last_error);
  }, [agent.state, agent.last_error]);

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
            void refreshAgents({ silent: true });
          }
        })
        .catch(() => {});
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [localState, agent.agent_id, onStateChange, refreshAgents]);

  const isTransient = TRANSIENT.has(localState);
  const switchChecked = localState === "running" || localState === "starting";
  const chatReady = isAgentChatReady(localState);
  const meta = getStateMeta(localState);
  const friendlyError = formatAgentError(localError, t);

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
      await teamsApi.remove(agent.agent_id);
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
    navigate(`/chat/${agent.agent_id}`);
  }, [agent.agent_id, setActiveAgent, navigate]);

  return (
    <>
      <div className={`${styles.agentCard2} ${styles.teamCard}`}>
        <div className={styles.agentCard2Header}>
          <div className={`${styles.agentCard2Icon} ${styles.teamCardIcon}`}>
            <ExpertIcon
              iconUrl={teamPortraitUrl(agent.icon_url)}
              iconName={TEAM_ICON_NAME}
              size={40}
            />
          </div>

          <div className={styles.agentCard2TitleBlock}>
            <div className={styles.agentCard2NameRow}>
              <div className={styles.agentCard2Name}>{agent.name}</div>
              <span className={styles.teamCardBadge}>
                <Users size={10} strokeWidth={2.4} aria-hidden />
                {t("chat.teamBadge")}
              </span>
              <Tooltip title={formatAgentState(localState, t)}>
                <span
                  className={
                    meta.spin ? styles.stateDotSpin : styles.teamCardStateDot
                  }
                  style={!meta.spin ? { background: meta.color } : undefined}
                  aria-label={formatAgentState(localState, t)}
                />
              </Tooltip>
            </div>
          </div>

          <div className={styles.agentCard2HeaderActions}>
            <Switch
              size="small"
              checked={switchChecked}
              loading={isTransient || actionLoading}
              onChange={(checked) => void handleToggle(checked)}
              className={styles.agentCard2Switch}
            />
          </div>
        </div>

        {agent.description?.trim() ? (
          <p className={styles.teamCardDesc} title={agent.description}>
            {agent.description}
          </p>
        ) : null}

        <div className={styles.teamCardRoster}>
          <span className={styles.teamCardRosterLabel}>
            {t("experts.teams.memberAvatars")}
          </span>
          {visibleMembers.map((member) => (
            <Tooltip key={member.id} title={member.name}>
              <div
                className={styles.teamMemberAvatar}
                style={{
                  color: member.color,
                  background: `${member.color}1a`,
                }}
              >
                {member.iconUrl || member.iconName ? (
                  <ExpertIcon
                    iconUrl={member.iconUrl}
                    iconName={member.iconName}
                    size={member.iconUrl ? 22 : 13}
                  />
                ) : (
                  member.name.slice(0, 1)
                )}
              </div>
            </Tooltip>
          ))}
          {hiddenCount > 0 && (
            <span className={styles.teamMemberMore}>
              {t("experts.teams.memberMore", { count: hiddenCount })}
            </span>
          )}
        </div>

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

        <div className={styles.agentCard2Footer}>
          <Tooltip
            title={
              chatReady
                ? t("pageShell.workspace.title")
                : t("workspace.requiresRunning")
            }
            mouseEnterDelay={0.5}
          >
            <button
              type="button"
              className={styles.agentCard2EditBtn}
              disabled={!chatReady}
              onClick={() => setWorkspaceDrawerOpen(true)}
              aria-label={t("pageShell.workspace.title")}
            >
              <FolderOpen size={13} />
            </button>
          </Tooltip>

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
              <button
                type="button"
                className={styles.agentCard2DelBtn}
                aria-label={t("common.delete", "Delete")}
              >
                <Trash2 size={13} />
              </button>
            </Tooltip>
          </Popconfirm>

          <Dropdown
            menu={{
              items: [
                {
                  key: "memory",
                  icon: <Notebook size={14} />,
                  label: t("experts.teams.memoryBtn"),
                  onClick: () => setMemoryCatalogOpen(true),
                },
                {
                  key: "channels",
                  icon: <Waypoints size={14} />,
                  label: t("experts.channelsBtn"),
                  onClick: () => setChannelCatalogOpen(true),
                },
              ] satisfies MenuProps["items"],
            }}
            trigger={["click"]}
            placement="bottomRight"
          >
            <Tooltip title={t("common.more")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.agentCard2EditBtn}
                aria-label={t("common.more")}
              >
                <MoreHorizontal size={13} />
              </button>
            </Tooltip>
          </Dropdown>

          {chatReady ? (
            <button
              type="button"
              className={`${styles.agentCard2ChatBtn} ${styles.teamCardChatBtn}`}
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
              className={`${styles.agentCard2ChatBtn} ${styles.teamCardChatBtn}`}
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
      <ChannelCatalogDrawer
        agentId={agent.agent_id}
        open={channelCatalogOpen}
        onClose={() => setChannelCatalogOpen(false)}
      />
      <MemoryCatalogDrawer
        agentId={agent.agent_id}
        open={memoryCatalogOpen}
        onClose={() => setMemoryCatalogOpen(false)}
        title={t("experts.teams.memoryTitle")}
      />
    </>
  );
});
