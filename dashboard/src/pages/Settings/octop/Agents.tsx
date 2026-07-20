/**
 * Admin → Agents — all users' agents overview.
 *
 * Card / table toggle, owner column, lifecycle actions (no create here).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Table,
  Button,
  Tag,
  Space,
  message,
  Popconfirm,
  Tooltip,
  Typography,
  Card,
  Segmented,
  Empty,
  Spin,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  RefreshCw,
  AlertCircle,
  Cpu,
  LayoutGrid,
  List,
  Play,
  Square,
  Trash2,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { formatAgentError } from "../../../utils/agentError";
import type { OctopAgent } from "../../../context/AgentContext";
import PageShell from "../../../layouts/PageShell";
import AgentProfileDrawer from "../../../components/AgentProfileDrawer";
import { AdminAgentCard } from "./AdminAgentCard";
import styles from "./agents.module.less";

const { Text } = Typography;

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

type ViewMode = "card" | "table";
const VIEW_STORAGE_KEY = "octop:admin-agents-view";

function loadViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_STORAGE_KEY);
  return stored === "table" ? "table" : "card";
}

export default function OctopAgentsPage() {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<OctopAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const { viewMode, setViewMode, showCardView } = useCardTableView(
    loadViewMode(),
  );
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [detailAgent, setDetailAgent] = useState<OctopAgent | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<OctopAgent[]>("/agents?scope=all");
      setAgents(data);
    } catch (err: unknown) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.loadFailed"),
      );
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onViewChange = (value: string | number) => {
    const mode = value === "table" ? "table" : "card";
    setViewMode(mode);
    localStorage.setItem(VIEW_STORAGE_KEY, mode);
  };

  const onAct = useCallback(
    async (row: OctopAgent, action: "start" | "stop" | "reload") => {
      setActionLoadingId(row.agent_id);
      try {
        await request(`/agents/${row.agent_id}/${action}`, { method: "POST" });
        message.success(t(`adminAgents.action.${action}Success`));
        void refresh();
      } catch (err: unknown) {
        message.error(
          err instanceof Error
            ? err.message
            : t(`adminAgents.action.${action}Failed`),
        );
      } finally {
        setActionLoadingId(null);
      }
    },
    [refresh, t],
  );

  const onDelete = useCallback(
    async (row: OctopAgent) => {
      setActionLoadingId(row.agent_id);
      try {
        await request(`/agents/${row.agent_id}`, { method: "DELETE" });
        message.success(t("adminAgents.action.deleteSuccess"));
        void refresh();
      } catch (err: unknown) {
        message.error(
          err instanceof Error ? err.message : t("common.deleteFailed"),
        );
      } finally {
        setActionLoadingId(null);
      }
    },
    [refresh, t],
  );

  const columns: ColumnsType<OctopAgent> = useMemo(
    () => [
      {
        title: t("adminAgents.columns.name"),
        dataIndex: "name",
        width: 140,
        fixed: "left",
        render: (name: string, row: OctopAgent) => (
          <button
            type="button"
            className={styles.nameLink}
            onClick={() => setDetailAgent(row)}
          >
            {name}
          </button>
        ),
      },
      {
        title: t("adminAgents.columns.agentId"),
        dataIndex: "agent_id",
        width: 200,
        ellipsis: { showTitle: true },
        render: (id: string) => (
          <Tooltip title={t("adminAgents.copyAgentId")}>
            <Text
              code
              copyable={{
                text: id,
                tooltips: [t("common.copy"), t("common.copied")],
              }}
              style={{ fontSize: 11 }}
            >
              {id}
            </Text>
          </Tooltip>
        ),
      },
      {
        title: t("adminAgents.columns.owner"),
        dataIndex: "owner_username",
        width: 120,
        render: (owner: string | undefined, row: OctopAgent) =>
          owner ? (
            <Tag icon={<User size={11} />}>{owner}</Tag>
          ) : row.user_id != null ? (
            <Tag icon={<User size={11} />}>#{row.user_id}</Tag>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: t("adminAgents.columns.description"),
        dataIndex: "description",
        ellipsis: { showTitle: false },
        render: (desc: string | null) =>
          desc ? (
            <Tooltip title={desc}>
              <span className={styles.descCell}>{desc}</span>
            </Tooltip>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: t("adminAgents.columns.template"),
        dataIndex: "template_name",
        width: 120,
        render: (value: string | null) =>
          value ? (
            <Tag color="blue">{value}</Tag>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: t("adminAgents.columns.model"),
        dataIndex: "default_model",
        width: 180,
        ellipsis: true,
        render: (model: string | null) =>
          model ? (
            <Space size={4}>
              <Cpu size={12} />
              <Text code style={{ fontSize: 12 }}>
                {model}
              </Text>
            </Space>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: t("adminAgents.columns.persona"),
        dataIndex: "persona_mbti",
        width: 88,
        render: (value: string | null) => <Tag>{value || "default"}</Tag>,
      },
      {
        title: t("adminAgents.columns.state"),
        dataIndex: "state",
        width: 110,
        render: (state: string, row) => (
          <Space size={6}>
            <Tag color={STATE_COLORS[state] ?? "default"}>
              {t(`adminAgents.state.${state}`, state)}
            </Tag>
            {row.last_error && (
              <Tooltip title={formatAgentError(row.last_error, t)}>
                <AlertCircle size={14} color="var(--fn-color-error, #ff4d4f)" />
              </Tooltip>
            )}
          </Space>
        ),
      },
      {
        title: t("adminAgents.columns.actions"),
        key: "actions",
        width: 140,
        fixed: "right",
        render: (_, row) => {
          const busy = actionLoadingId === row.agent_id;
          return (
            <div className={styles.actionGroup}>
              {STARTABLE.has(row.state) && (
                <Tooltip title={t("adminAgents.action.start")}>
                  <Button
                    type="text"
                    size="small"
                    icon={<Play size={14} />}
                    loading={busy}
                    onClick={() => void onAct(row, "start")}
                  />
                </Tooltip>
              )}
              {row.state === "running" && (
                <Tooltip title={t("adminAgents.action.stop")}>
                  <Button
                    type="text"
                    size="small"
                    icon={<Square size={14} />}
                    loading={busy}
                    onClick={() => void onAct(row, "stop")}
                  />
                </Tooltip>
              )}
              <Tooltip title={t("adminAgents.action.reload")}>
                <Button
                  type="text"
                  size="small"
                  icon={<RefreshCw size={14} />}
                  loading={busy}
                  onClick={() => void onAct(row, "reload")}
                />
              </Tooltip>
              <Popconfirm
                title={t("adminAgents.confirmDelete", { name: row.name })}
                okText={t("common.delete")}
                cancelText={t("common.cancel")}
                okButtonProps={{ danger: true }}
                onConfirm={() => void onDelete(row)}
              >
                <Tooltip title={t("common.delete")}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<Trash2 size={14} />}
                    loading={busy}
                  />
                </Tooltip>
              </Popconfirm>
            </div>
          );
        },
      },
    ],
    [actionLoadingId, t, onAct, onDelete],
  );

  return (
    <PageShell
      title={t("pageShell.adminAgents.title")}
      subtitle={t("pageShell.adminAgents.subtitle")}
      actions={
        <Button icon={<RefreshCw size={14} />} onClick={() => void refresh()}>
          {t("common.refresh")}
        </Button>
      }
    >
      <div className={styles.toolbar}>
        <Text type="secondary">
          {t("adminAgents.total", { count: agents.length })}
        </Text>
        <Segmented
          value={viewMode}
          onChange={onViewChange}
          options={[
            {
              value: "card",
              label: (
                <Space size={6}>
                  <LayoutGrid size={14} />
                  {t("adminAgents.viewCard")}
                </Space>
              ),
            },
            {
              value: "table",
              label: (
                <Space size={6}>
                  <List size={14} />
                  {t("adminAgents.viewTable")}
                </Space>
              ),
            },
          ]}
        />
      </div>

      {!loading && agents.length === 0 ? (
        <Empty description={t("adminAgents.empty")} />
      ) : showCardView ? (
        <Spin spinning={loading}>
          <div className={styles.cardGrid}>
            {agents.map((agent) => (
              <AdminAgentCard
                key={agent.agent_id}
                agent={agent}
                onRefresh={() => void refresh()}
                onOpenDetail={setDetailAgent}
              />
            ))}
          </div>
        </Spin>
      ) : (
        <Card className={styles.tableCard} bordered={false}>
          <Table<OctopAgent>
            rowKey="agent_id"
            loading={loading}
            dataSource={agents}
            columns={columns}
            scroll={{ x: 1200 }}
            pagination={{
              defaultPageSize: 10,
              showSizeChanger: true,
              pageSizeOptions: ["10", "20", "50"],
              showTotal: (total) => t("adminAgents.total", { count: total }),
            }}
          />
        </Card>
      )}

      <AgentProfileDrawer
        open={detailAgent !== null}
        agent={detailAgent}
        onClose={() => setDetailAgent(null)}
      />
    </PageShell>
  );
}
