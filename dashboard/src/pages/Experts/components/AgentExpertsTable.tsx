// dashboard/src/pages/Experts/components/AgentExpertsTable.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Popconfirm, Switch, Table, Tag, Tooltip, message } from "antd";
import type { ColumnsType } from "antd/es/table";
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
import { request } from "../../../api/request";
import type { OctopAgent } from "../../../context/AgentContext";
import { useAgent } from "../../../context/AgentContext";
import MbtiPersonaTag from "../../../components/MbtiPersonaTag";
import MbtiCatalogDrawer from "./MbtiCatalogDrawer";
import { iconForName } from "./iconForName";
import {
  isAgentChatReady,
  formatAgentState,
  formatAgentError,
  isAgentModelConfigError,
} from "../../../utils/agentError";
import styles from "../index.module.less";

const STATE_COLORS: Record<string, string> = {
  running: "success",
  stopped: "default",
  failed: "error",
  starting: "processing",
  stopping: "processing",
  created: "default",
};

const TRANSIENT = new Set(["starting", "stopping"]);

interface AgentExpertsTableProps {
  agents: OctopAgent[];
  onEdit: (agentId: string) => void;
  onDeleted: (agentId: string) => void;
  onStateChange: (agentId: string, newState: string) => void;
}

export default function AgentExpertsTable({
  agents,
  onEdit,
  onDeleted,
  onStateChange,
}: AgentExpertsTableProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setActiveAgent, refresh: refreshAgents } = useAgent();
  const [localStates, setLocalStates] = useState<Record<string, string>>({});
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [workspaceAgentId, setWorkspaceAgentId] = useState<string | null>(null);
  const [skillCatalogAgentId, setSkillCatalogAgentId] = useState<string | null>(
    null,
  );
  const [subagentCatalogAgentId, setSubagentCatalogAgentId] = useState<
    string | null
  >(null);
  const [installedSubagentSlugs, setInstalledSubagentSlugs] = useState<
    Set<string>
  >(() => new Set());
  const [mbtiCatalogOpen, setMbtiCatalogOpen] = useState(false);
  const [mbtiAgentId, setMbtiAgentId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const openMbtiCatalog = useCallback((agentId: string) => {
    setMbtiAgentId(agentId);
    setMbtiCatalogOpen(true);
  }, []);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const a of agents) next[a.agent_id] = a.state;
    setLocalStates(next);
  }, [agents]);

  useEffect(() => {
    const transientIds = agents
      .map((a) => a.agent_id)
      .filter((id) => TRANSIENT.has(localStates[id] ?? ""));
    if (transientIds.length === 0) {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
      return;
    }
    pollRef.current = setInterval(() => {
      for (const id of transientIds) {
        request<{ state: string; last_error: string | null }>(
          `/agents/${id}/status`,
        )
          .then((s) => {
            setLocalStates((prev) => ({ ...prev, [id]: s.state }));
            onStateChange(id, s.state);
            if (!TRANSIENT.has(s.state)) {
              void refreshAgents({ silent: true });
            }
          })
          .catch(() => {});
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [agents, localStates, onStateChange, refreshAgents]);

  const handleToggle = useCallback(
    async (agent: OctopAgent, checked: boolean) => {
      setActionLoadingId(agent.agent_id);
      try {
        if (checked) {
          await request(`/agents/${agent.agent_id}/start`, { method: "POST" });
          setLocalStates((prev) => ({ ...prev, [agent.agent_id]: "starting" }));
          onStateChange(agent.agent_id, "starting");
          message.success(t("experts.agentStarted", { name: agent.name }));
        } else {
          await request(`/agents/${agent.agent_id}/stop`, { method: "POST" });
          setLocalStates((prev) => ({ ...prev, [agent.agent_id]: "stopping" }));
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
        setActionLoadingId(null);
      }
    },
    [t, onStateChange],
  );

  const handleDelete = useCallback(
    async (agent: OctopAgent) => {
      setActionLoadingId(agent.agent_id);
      try {
        await request(`/agents/${agent.agent_id}`, { method: "DELETE" });
        message.success(t("experts.agentDeleted", { name: agent.name }));
        onDeleted(agent.agent_id);
      } catch {
        message.error(t("experts.agentDeleteFailed"));
      } finally {
        setActionLoadingId(null);
      }
    },
    [t, onDeleted],
  );

  const handleReload = useCallback(
    async (agent: OctopAgent) => {
      setActionLoadingId(agent.agent_id);
      try {
        await request(`/agents/${agent.agent_id}/reload`, { method: "POST" });
        message.success(t("experts.agentReloadSuccess", { name: agent.name }));
      } catch {
        message.error(t("experts.agentReloadFailed"));
      } finally {
        setActionLoadingId(null);
      }
    },
    [t],
  );

  const handleOpenChat = useCallback(
    (agentId: string) => {
      setActiveAgent(agentId);
      navigate("/chat");
    },
    [setActiveAgent, navigate],
  );

  const copyAgentId = useCallback(
    async (agentId: string) => {
      try {
        await navigator.clipboard.writeText(agentId);
        message.success(t("common.copied"));
      } catch {
        message.error(t("common.copyFailed"));
      }
    },
    [t],
  );

  const openSubagentCatalog = useCallback((agentId: string) => {
    setSubagentCatalogAgentId(agentId);
    request<{ slug: string }[]>(`/agents/${agentId}/subagents`)
      .then((rows) =>
        setInstalledSubagentSlugs(new Set(rows.map((r) => r.slug))),
      )
      .catch(() => setInstalledSubagentSlugs(new Set()));
  }, []);

  const closeSubagentCatalog = useCallback(() => {
    setSubagentCatalogAgentId(null);
  }, []);

  const columns: ColumnsType<OctopAgent> = [
    {
      title: t("experts.table.name", "名称"),
      dataIndex: "name",
      width: 160,
      fixed: "left",
      render: (name: string, row) => (
        <div className={styles.tableNameCell}>
          <span
            className={styles.tableIcon}
            style={{
              color: row.color || "#6366f1",
              background: `${row.color || "#6366f1"}1a`,
            }}
          >
            {iconForName(row.icon_name, 16)}
          </span>
          <span className={styles.tableNameText}>{name}</span>
        </div>
      ),
    },
    {
      title: t("experts.table.agentId", "专家 ID"),
      dataIndex: "agent_id",
      width: 100,
      ellipsis: true,
      render: (agentId: string) => (
        <Tooltip title={t("experts.copyAgentId")}>
          <button
            type="button"
            className={styles.tableAgentIdBtn}
            onClick={() => void copyAgentId(agentId)}
          >
            <span className={styles.tableAgentIdValue}>{agentId}</span>
            <Copy size={11} className={styles.tableAgentIdIcon} />
          </button>
        </Tooltip>
      ),
    },
    {
      title: t("experts.table.state", "状态"),
      dataIndex: "state",
      width: 200,
      render: (_state, row) => {
        const state = localStates[row.agent_id] ?? row.state;
        const friendlyError =
          state === "failed" && row.last_error
            ? formatAgentError(row.last_error, t)
            : "";
        return (
          <div className={styles.tableStateCell}>
            <Tag color={STATE_COLORS[state] ?? "default"}>
              {formatAgentState(state, t)}
            </Tag>
            {friendlyError ? (
              <div className={styles.tableErrorWrap}>
                <Tooltip title={friendlyError} overlayStyle={{ maxWidth: 360 }}>
                  <div className={styles.tableErrorText}>
                    <AlertCircle size={12} />
                    <span>{friendlyError}</span>
                  </div>
                </Tooltip>
                {isAgentModelConfigError(row.last_error) && (
                  <button
                    type="button"
                    className={styles.tableErrorAction}
                    onClick={() => navigate("/admin/models")}
                  >
                    {t("modelConfig.configureButton")}
                  </button>
                )}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t("experts.table.description", "描述"),
      dataIndex: "description",
      ellipsis: true,
      render: (desc: string | null | undefined) => desc || "—",
    },
    {
      title: t("experts.table.model", "模型"),
      dataIndex: "default_model",
      width: 140,
      ellipsis: true,
      render: (model: string | null | undefined) => model || "—",
    },
    {
      title: t("experts.table.persona", "人格"),
      dataIndex: "persona_mbti",
      width: 120,
      render: (value: string | null, row) => (
        <MbtiPersonaTag
          value={value}
          onClick={() => openMbtiCatalog(row.agent_id)}
        />
      ),
    },
    {
      title: t("experts.table.actions", "操作"),
      key: "actions",
      width: 340,
      fixed: "right",
      render: (_v, row) => {
        const state = localStates[row.agent_id] ?? row.state;
        const isTransient = TRANSIENT.has(state);
        const switchChecked = state === "running" || state === "starting";
        const chatReady = isAgentChatReady(state);
        return (
          <div className={styles.tableActions}>
            <Tooltip title={t("experts.reloadAgent")}>
              <button
                type="button"
                className={styles.tableActionBtn}
                disabled={isTransient || actionLoadingId === row.agent_id}
                onClick={() => void handleReload(row)}
              >
                <RefreshCw size={13} />
              </button>
            </Tooltip>
            <Switch
              size="small"
              checked={switchChecked}
              loading={isTransient || actionLoadingId === row.agent_id}
              onChange={(checked) => void handleToggle(row, checked)}
            />
            <Tooltip
              title={t("pageShell.workspace.title")}
              mouseEnterDelay={0.5}
            >
              <button
                type="button"
                className={styles.tableActionBtn}
                onClick={() => setWorkspaceAgentId(row.agent_id)}
                aria-label={t("pageShell.workspace.title")}
              >
                <FolderOpen size={13} />
              </button>
            </Tooltip>
            <Tooltip title={t("experts.skillsBtn")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.tableActionBtn}
                onClick={() => setSkillCatalogAgentId(row.agent_id)}
                aria-label={t("experts.skillsBtn")}
              >
                <Sparkles size={13} />
              </button>
            </Tooltip>
            <Tooltip title={t("experts.subagentsBtn")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.tableActionBtn}
                onClick={() => openSubagentCatalog(row.agent_id)}
                aria-label={t("experts.subagentsBtn")}
              >
                <Bot size={13} />
              </button>
            </Tooltip>
            <Tooltip title={t("common.edit", "Edit")} mouseEnterDelay={0.5}>
              <button
                type="button"
                className={styles.tableActionBtn}
                onClick={() => onEdit(row.agent_id)}
                aria-label={t("common.edit", "Edit")}
              >
                <Pencil size={13} />
              </button>
            </Tooltip>
            <Popconfirm
              title={t("experts.confirmDelete", { name: row.name })}
              description={t("experts.confirmDeleteHint")}
              onConfirm={() => void handleDelete(row)}
              okText={t("common.delete", "Delete")}
              cancelText={t("common.cancel")}
              okButtonProps={{ danger: true }}
            >
              <Tooltip
                title={t("common.delete", "Delete")}
                mouseEnterDelay={0.5}
              >
                <button type="button" className={styles.tableActionBtn}>
                  <Trash2 size={13} />
                </button>
              </Tooltip>
            </Popconfirm>
            {chatReady ? (
              <button
                type="button"
                className={styles.tableChatBtn}
                onClick={() => handleOpenChat(row.agent_id)}
              >
                <MessageSquare size={13} />
                {t("experts.openChat", "对话")}
                <ChevronRight size={13} />
              </button>
            ) : state === "failed" ||
              state === "stopped" ||
              state === "created" ? (
              <button
                type="button"
                className={styles.tableChatBtn}
                disabled={isTransient || actionLoadingId === row.agent_id}
                onClick={() => void handleToggle(row, true)}
              >
                {state === "failed"
                  ? t("experts.retryStart", "重试启动")
                  : t("experts.startAgent", "启动")}
              </button>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <>
      <Table<OctopAgent>
        className={styles.expertsTable}
        rowKey="agent_id"
        dataSource={agents}
        columns={columns}
        scroll={{ x: 1304 }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          pageSizeOptions: ["10", "20", "50"],
          showTotal: (total) => t("experts.totalAgents", { count: total }),
        }}
      />
      <WorkspaceDrawer
        agentId={workspaceAgentId ?? ""}
        open={workspaceAgentId !== null}
        onClose={() => setWorkspaceAgentId(null)}
      />
      <SkillCatalogDrawer
        agentId={skillCatalogAgentId ?? ""}
        open={skillCatalogAgentId !== null}
        onClose={() => setSkillCatalogAgentId(null)}
      />
      <SubagentCatalogDrawer
        agentId={subagentCatalogAgentId ?? ""}
        agentState={
          subagentCatalogAgentId
            ? localStates[subagentCatalogAgentId] ?? "stopped"
            : "stopped"
        }
        open={subagentCatalogAgentId !== null}
        installedSlugs={installedSubagentSlugs}
        onClose={closeSubagentCatalog}
        onInstalled={() => {
          if (subagentCatalogAgentId) {
            request<{ slug: string }[]>(
              `/agents/${subagentCatalogAgentId}/subagents`,
            )
              .then((rows) =>
                setInstalledSubagentSlugs(new Set(rows.map((r) => r.slug))),
              )
              .catch(() => setInstalledSubagentSlugs(new Set()));
          }
        }}
      />
      <MbtiCatalogDrawer
        open={mbtiCatalogOpen}
        agentId={mbtiAgentId}
        onClose={() => {
          setMbtiCatalogOpen(false);
          setMbtiAgentId(null);
        }}
        onApplied={() => {
          setMbtiCatalogOpen(false);
          setMbtiAgentId(null);
          void refreshAgents({ silent: true, force: true });
        }}
      />
    </>
  );
}
