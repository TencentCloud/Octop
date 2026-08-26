import { memo, useCallback, useState } from "react";
import { Popconfirm, Tag, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";
import { copyText } from "@/utils/copyText";

import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Copy,
  Cpu,
  Play,
  RefreshCw,
  Square,
  Trash2,
  User,
} from "lucide-react";
import { request } from "../../../api/request";
import type { OctopAgent } from "../../../context/AgentContext";
import MbtiPersonaTag from "../../../components/MbtiPersonaTag";
import { formatAgentError } from "../../../utils/agentError";
import { iconForName } from "../../Experts/components/iconForName";
import styles from "./agents.module.less";

const STATE_COLORS: Record<string, string> = {
  running: "success",
  stopped: "default",
  failed: "error",
  starting: "processing",
  stopping: "processing",
  created: "default",
  error: "error",
  unknown: "default",
};

const STARTABLE = new Set(["stopped", "created", "error", "failed"]);

interface AdminAgentCardProps {
  agent: OctopAgent;
  onRefresh: () => void;
  onOpenDetail?: (agent: OctopAgent) => void;
}

export const AdminAgentCard = memo(function AdminAgentCard({
  agent,
  onRefresh,
  onOpenDetail,
}: AdminAgentCardProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const accent = agent.color || "#6366f1";

  const onAct = useCallback(
    async (action: "start" | "stop" | "reload") => {
      setLoading(true);
      try {
        await request(`/agents/${agent.agent_id}/${action}`, {
          method: "POST",
        });
        message.success(t(`adminAgents.action.${action}Success`));
        onRefresh();
      } catch (err) {
        message.error(
          err instanceof Error
            ? err.message
            : t(`adminAgents.action.${action}Failed`),
        );
      } finally {
        setLoading(false);
      }
    },
    [agent.agent_id, onRefresh, t],
  );

  const onDelete = useCallback(async () => {
    setLoading(true);
    try {
      await request(`/agents/${agent.agent_id}`, { method: "DELETE" });
      message.success(t("adminAgents.action.deleteSuccess"));
      onRefresh();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.deleteFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [agent.agent_id, onRefresh, t]);

  const copyAgentId = useCallback(async () => {
    const ok = await copyText(agent.agent_id);
    if (ok) message.success(t("common.copied"));
    else message.error(t("common.copyFailed"));
  }, [agent.agent_id, t]);

  return (
    <div
      className={styles.agentCard}
      style={{ "--agent-accent": accent } as React.CSSProperties}
    >
      <div className={styles.agentCardAccent} />
      <div className={styles.agentCardBody}>
        <div className={styles.agentCardHeader}>
          <div
            className={styles.agentCardIcon}
            style={{ color: accent, background: `${accent}1a` }}
          >
            {iconForName(agent.icon_name, 20)}
          </div>
          <div className={styles.agentCardTitleBlock}>
            <button
              type="button"
              className={styles.agentCardNameBtn}
              onClick={() => onOpenDetail?.(agent)}
              disabled={!onOpenDetail}
            >
              {agent.name}
            </button>
            <Tooltip title={t("adminAgents.copyAgentId")}>
              <button
                type="button"
                className={styles.agentCardId}
                onClick={() => void copyAgentId()}
              >
                <span className={styles.agentCardIdLabel}>
                  {t("adminAgents.agentId")}
                </span>
                <span className={styles.agentCardIdValue}>
                  {agent.agent_id}
                </span>
                <Copy size={11} className={styles.agentCardIdIcon} />
              </button>
            </Tooltip>
            <div className={styles.agentCardMeta}>
              <Tag color={STATE_COLORS[agent.state] ?? "default"}>
                {t(`adminAgents.state.${agent.state}`, agent.state)}
              </Tag>
              {agent.owner_username ? (
                <Tag icon={<User size={11} />} className={styles.ownerTag}>
                  {agent.owner_username}
                </Tag>
              ) : agent.user_id != null ? (
                <Tag icon={<User size={11} />} className={styles.ownerTag}>
                  #{agent.user_id}
                </Tag>
              ) : null}
              {agent.template_name && (
                <Tag color="blue">{agent.template_name}</Tag>
              )}
              <MbtiPersonaTag value={agent.persona_mbti} />
            </div>
          </div>
        </div>

        {agent.description && (
          <p className={styles.agentCardDesc}>{agent.description}</p>
        )}

        {agent.default_model && (
          <div className={styles.agentCardModel}>
            <Cpu size={12} style={{ marginRight: 4, verticalAlign: -2 }} />
            {agent.default_model}
          </div>
        )}

        {agent.last_error && (
          <Tooltip title={formatAgentError(agent.last_error, t)}>
            <Tag color="error" icon={<AlertCircle size={12} />}>
              {t("adminAgents.hasError")}
            </Tag>
          </Tooltip>
        )}

        <div className={styles.agentCardFooter}>
          <div className={styles.agentCardActions}>
            {STARTABLE.has(agent.state) && (
              <Tooltip title={t("adminAgents.action.start")}>
                <button
                  type="button"
                  className={`${styles.cardActionBtn} ${styles.cardActionBtnStart}`}
                  disabled={loading}
                  onClick={() => void onAct("start")}
                >
                  <Play size={14} />
                </button>
              </Tooltip>
            )}
            {agent.state === "running" && (
              <Tooltip title={t("adminAgents.action.stop")}>
                <button
                  type="button"
                  className={`${styles.cardActionBtn} ${styles.cardActionBtnStop}`}
                  disabled={loading}
                  onClick={() => void onAct("stop")}
                >
                  <Square size={14} />
                </button>
              </Tooltip>
            )}
            <Tooltip title={t("adminAgents.action.reload")}>
              <button
                type="button"
                className={`${styles.cardActionBtn} ${styles.cardActionBtnReload}`}
                disabled={loading}
                onClick={() => void onAct("reload")}
              >
                <RefreshCw
                  size={14}
                  className={loading ? styles.spinIcon : undefined}
                />
              </button>
            </Tooltip>
          </div>
          <Popconfirm
            title={t("adminAgents.confirmDelete", { name: agent.name })}
            okText={t("common.delete")}
            cancelText={t("common.cancel")}
            okButtonProps={{ danger: true }}
            onConfirm={() => void onDelete()}
          >
            <Tooltip title={t("common.delete")}>
              <button
                type="button"
                className={`${styles.cardActionBtn} ${styles.cardActionBtnDanger}`}
                disabled={loading}
              >
                <Trash2 size={14} />
              </button>
            </Tooltip>
          </Popconfirm>
        </div>
      </div>
    </div>
  );
});
