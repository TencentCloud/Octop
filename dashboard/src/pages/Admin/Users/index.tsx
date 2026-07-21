/**
 * Admin → Users page (plan §14.7).
 *
 * List all users with role/disabled toggles, password reset, delete.
 * Card and table views; default is card on mobile, table on desktop. The view switcher + refresh +
 * new-user buttons live in a content-area toolbar (mirrors the Experts
 * page layout). Each row/card shows agent count; click opens a drawer
 * with that user's agents.
 *
 * Endpoints (all require admin role; backend returns 403 otherwise):
 *   GET    /api/users
 *   POST   /api/users
 *   PATCH  /api/users/{id}
 *   POST   /api/users/{id}/reset-password
 *   DELETE /api/users/{id}
 */

import { useEffect, useMemo, useState, useCallback } from "react";
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  Popconfirm,
  message,
  Switch,
  Typography,
  Tooltip,
  Drawer,
  Empty,
  Spin,
  Tag,
  Segmented,
} from "antd";
import {
  Bot,
  ChevronRight,
  Clock,
  IdCard,
  KeyRound,
  LayoutGrid,
  List,
  Lock,
  LockOpen,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { request } from "../../../api/request";
import { authApi } from "../../../api/modules/auth";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import type { OctopAgent } from "../../../context/AgentContext";
import { AgentCard } from "../../Experts/components/AgentCard";
import EditAgentDrawer from "../../Experts/components/EditAgentDrawer";
import expertStyles from "../../Experts/index.module.less";
import styles from "./index.module.less";

const { Text } = Typography;

interface UserRow {
  id: number;
  username: string;
  role: "admin" | "user";
  display_name: string | null;
  disabled: boolean;
  login_failed_count?: number;
  login_locked?: boolean;
  login_locked_until?: number;
  login_retry_after_seconds?: number;
  created_at?: number;
}

interface CreateValues {
  username: string;
  display_name?: string;
  password: string;
  confirm: string;
  role: "admin" | "user";
}

interface ResetValues {
  password: string;
  confirm: string;
}

interface RoleMeta {
  color: string;
  bg: string;
}

const ROLE_META: Record<"admin" | "user", RoleMeta> = {
  admin: { color: "#d4880e", bg: "rgba(212,136,14,0.10)" },
  user: { color: "#1677ff", bg: "rgba(22,119,255,0.10)" },
};

function useNowSeconds(active: boolean): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(
      () => setNow(Math.floor(Date.now() / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function lockRemainingSeconds(row: UserRow, nowSec: number): number {
  if (!row.login_locked || !row.login_locked_until) return 0;
  return Math.max(0, row.login_locked_until - nowSec);
}

function formatUserTs(ts: number | undefined, timeZone: string): string {
  if (!ts) return "—";
  return formatServerDateTime(ts, timeZone);
}

interface UserCardGridProps {
  rows: UserRow[];
  loading: boolean;
  agentsByUserId: Map<number, OctopAgent[]>;
  agentsLoading: boolean;
  currentUserId: number | null;
  roleOptions: { value: "admin" | "user"; label: string }[];
  onTogglePatch: (
    row: UserRow,
    patch: Partial<Pick<UserRow, "role" | "disabled">>,
  ) => Promise<void>;
  onShowAgents: (row: UserRow) => void;
  onResetPassword: (row: UserRow) => void;
  onDelete: (row: UserRow) => Promise<void>;
  onUnlockLogin: (row: UserRow) => Promise<void>;
  nowSec: number;
  isSelfAdmin: (row: UserRow) => boolean;
}

function userInitials(displayName: string, username: string): string {
  const source = displayName.trim() || username;
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function UserCardGrid({
  rows,
  loading,
  agentsByUserId,
  agentsLoading,
  currentUserId,
  roleOptions,
  onTogglePatch,
  onShowAgents,
  onResetPassword,
  onDelete,
  onUnlockLogin,
  nowSec,
  isSelfAdmin,
}: UserCardGridProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  if (loading && rows.length === 0) {
    return (
      <div className={styles.userGridLoading}>
        <Spin />
      </div>
    );
  }
  if (rows.length === 0) {
    return <Empty description={t("adminUsers.noUsers")} />;
  }
  return (
    <div className={styles.userCardGrid}>
      {rows.map((row) => {
        const agentCount = agentsByUserId.get(row.id)?.length ?? 0;
        const isSelf = row.id === currentUserId;
        const displayName = row.display_name?.trim() || row.username;
        const remaining = lockRemainingSeconds(row, nowSec);
        const isLocked = remaining > 0;
        const roleMeta = ROLE_META[row.role] ?? ROLE_META.user;
        const failedCount = row.login_failed_count ?? 0;
        const accentColor = isLocked
          ? "#ff4d4f"
          : row.disabled
          ? "#8c8c8c"
          : roleMeta.color;
        const statusColor = row.disabled ? "#8c8c8c" : "#52c41a";
        const statusBg = row.disabled
          ? "rgba(140,140,140,0.10)"
          : "rgba(82,196,26,0.10)";
        return (
          <div
            key={row.id}
            className={[
              styles.userCard,
              isLocked ? styles.userCardLocked : "",
              row.disabled ? styles.userCardDisabled : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <div
              className={styles.userCardAccent}
              style={{ background: accentColor }}
            />

            <div className={styles.userCardInner}>
              <div className={styles.userCardHeader}>
                <div
                  className={styles.userCardAvatar}
                  style={{ color: roleMeta.color, background: roleMeta.bg }}
                  aria-hidden="true"
                >
                  {userInitials(displayName, row.username)}
                </div>

                <div className={styles.userCardTitleBlock}>
                  <div className={styles.userCardNameRow}>
                    <span className={styles.userCardName}>{displayName}</span>
                    {isSelf && (
                      <Tag color="blue" className={styles.userCardYouTag}>
                        {t("adminUsers.you")}
                      </Tag>
                    )}
                  </div>
                  <div className={styles.userCardHandle}>@{row.username}</div>
                  {row.created_at != null && (
                    <Tooltip title={t("adminUsers.colCreatedAt")}>
                      <div className={styles.userCardTime}>
                        <Clock size={11} />
                        <span>{formatUserTs(row.created_at, timeZone)}</span>
                      </div>
                    </Tooltip>
                  )}
                  <div className={styles.userCardMeta}>
                    <Tooltip
                      title={
                        isSelfAdmin(row)
                          ? t("adminUsers.demoteSelf")
                          : undefined
                      }
                    >
                      <Select
                        size="small"
                        value={row.role}
                        options={roleOptions}
                        disabled={isSelfAdmin(row)}
                        onChange={(v) => void onTogglePatch(row, { role: v })}
                        className={styles.userCardRoleSelect}
                        popupMatchSelectWidth={false}
                        style={{
                          background: roleMeta.bg,
                          color: roleMeta.color,
                          borderRadius: 20,
                        }}
                      />
                    </Tooltip>
                    <span
                      className={styles.userCardPill}
                      style={{ color: statusColor, background: statusBg }}
                    >
                      <span
                        className={styles.userCardStatusDot}
                        style={{ background: statusColor }}
                      />
                      {row.disabled
                        ? t("adminUsers.statusDisabled")
                        : t("adminUsers.statusEnabled")}
                    </span>
                  </div>
                </div>

                <Switch
                  size="small"
                  checked={!row.disabled}
                  onChange={(checked) =>
                    void onTogglePatch(row, { disabled: !checked })
                  }
                  className={styles.userCardSwitch}
                  aria-label={t("common.enabled")}
                />
              </div>

              <div className={styles.userCardStats}>
                <button
                  type="button"
                  className={styles.userCardStatBtn}
                  onClick={() => onShowAgents(row)}
                >
                  <Bot size={15} />
                  <span>{t("adminUsers.colAgents")}</span>
                  <span className={styles.userCardStatCount}>
                    {agentsLoading ? "…" : agentCount}
                  </span>
                  <ChevronRight size={14} />
                </button>
              </div>

              {isLocked && (
                <div className={styles.userCardLockAlert}>
                  <Lock size={14} />
                  <span className={styles.userCardLockText}>
                    {t("adminUsers.loginLockActive", {
                      minutes: Math.max(1, Math.ceil(remaining / 60)),
                    })}
                  </span>
                  <Button
                    type="link"
                    size="small"
                    className={styles.userCardLockUnlock}
                    onClick={() => void onUnlockLogin(row)}
                  >
                    {t("adminUsers.unlockLogin")}
                  </Button>
                </div>
              )}

              {!isLocked && failedCount > 0 && (
                <div className={styles.userCardFailedHint}>
                  {t("adminUsers.loginFailedCount", { count: failedCount })}
                </div>
              )}

              <div className={styles.userCardFooter}>
                <Tooltip
                  title={t("adminUsers.resetPassword")}
                  mouseEnterDelay={0.5}
                >
                  <button
                    type="button"
                    className={styles.userCardIconBtn}
                    onClick={() => onResetPassword(row)}
                    aria-label={t("adminUsers.resetPassword")}
                  >
                    <KeyRound size={15} />
                  </button>
                </Tooltip>

                <Popconfirm
                  title={t("adminUsers.deleteConfirm", {
                    username: row.username,
                  })}
                  onConfirm={() => void onDelete(row)}
                  disabled={isSelf}
                >
                  <Tooltip
                    title={
                      isSelf ? t("adminUsers.deleteSelf") : t("common.delete")
                    }
                    mouseEnterDelay={0.5}
                  >
                    <button
                      type="button"
                      className={`${styles.userCardIconBtn} ${styles.userCardIconBtnDanger}`}
                      disabled={isSelf}
                      aria-label={t("common.delete")}
                    >
                      <Trash2 size={15} />
                    </button>
                  </Tooltip>
                </Popconfirm>

                <span className={styles.userCardFooterSpacer} />

                <span className={styles.userCardIdBadge}>#{row.id}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Compact login-lock status indicator. Used by both the card view
 * (inline in a `userCard2Row`) and the table view (table cell).
 */
function UserLoginLock({
  row,
  nowSec,
  onUnlock,
}: {
  row: UserRow;
  nowSec: number;
  onUnlock: () => void;
}) {
  const { t } = useTranslation();
  const failedCount = row.login_failed_count ?? 0;
  if (!row.login_locked) {
    if (failedCount > 0) {
      return (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t("adminUsers.loginFailedCount", { count: failedCount })}
        </Text>
      );
    }
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        {t("adminUsers.loginLockNone")}
      </Text>
    );
  }
  const remaining = lockRemainingSeconds(row, nowSec);
  const minutes = Math.max(1, Math.ceil(remaining / 60));
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap",
        justifyContent: "flex-end",
      }}
    >
      <Tag
        color="error"
        style={{ margin: 0, fontSize: 11, lineHeight: "18px" }}
      >
        {t("adminUsers.loginLockActive", { minutes })}
      </Tag>
      <Button
        size="small"
        type="link"
        onClick={onUnlock}
        style={{ padding: 0, fontSize: 12, height: "auto" }}
      >
        {t("adminUsers.unlockLogin")}
      </Button>
    </span>
  );
}

export default function AdminUsersPage() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [agents, setAgents] = useState<OctopAgent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<CreateValues>();
  const [resetTarget, setResetTarget] = useState<UserRow | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetForm] = Form.useForm<ResetValues>();
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [agentDrawerUser, setAgentDrawerUser] = useState<UserRow | null>(null);
  const [editAgent, setEditAgent] = useState<OctopAgent | null>(null);
  const { viewMode, setViewMode, showCardView } = useCardTableView("table");

  const roleOptions = [
    { value: "admin" as const, label: t("adminUsers.roleAdmin") },
    { value: "user" as const, label: t("adminUsers.roleUser") },
  ];

  const isSelfAdmin = useCallback(
    (row: UserRow) => row.id === currentUserId && row.role === "admin",
    [currentUserId],
  );

  const hasLockedUser = useMemo(
    () => rows.some((row) => row.login_locked),
    [rows],
  );
  const nowSec = useNowSeconds(hasLockedUser);

  const agentsByUserId = useMemo(() => {
    const map = new Map<number, OctopAgent[]>();
    for (const agent of agents) {
      if (agent.user_id == null) continue;
      const list = map.get(agent.user_id) ?? [];
      list.push(agent);
      map.set(agent.user_id, list);
    }
    return map;
  }, [agents]);

  const drawerAgents = agentDrawerUser
    ? agentsByUserId.get(agentDrawerUser.id) ?? []
    : [];

  const refreshUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<UserRow[]>("/users");
      setRows(data);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.loadFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!hasLockedUser) return;
    const anyExpired = rows.some(
      (row) => row.login_locked && lockRemainingSeconds(row, nowSec) === 0,
    );
    if (anyExpired) void refreshUsers();
  }, [hasLockedUser, nowSec, rows, refreshUsers]);

  const refreshAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const data = await request<OctopAgent[]>("/agents?scope=all");
      setAgents(data);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.loadFailed"),
      );
      setAgents([]);
    } finally {
      setAgentsLoading(false);
    }
  }, [t]);

  const patchAgent = useCallback(
    (agentId: string, patch: Partial<OctopAgent>) => {
      setAgents((prev) =>
        prev.map((a) => (a.agent_id === agentId ? { ...a, ...patch } : a)),
      );
    },
    [],
  );

  const handleDrawerStateChange = useCallback(
    (agentId: string, newState: string) => {
      patchAgent(agentId, { state: newState });
    },
    [patchAgent],
  );

  const handleDrawerDeleted = useCallback(
    (agentId: string) => {
      setAgents((prev) => prev.filter((a) => a.agent_id !== agentId));
      void refreshAgents();
    },
    [refreshAgents],
  );

  const handleEditSaved = useCallback(
    (
      updated: Pick<
        OctopAgent,
        "agent_id" | "name" | "description" | "default_model"
      >,
    ) => {
      setEditAgent(null);
      patchAgent(updated.agent_id, {
        name: updated.name,
        description: updated.description,
        default_model: updated.default_model,
      });
      void refreshAgents();
    },
    [patchAgent, refreshAgents],
  );

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshUsers(), refreshAgents()]);
  }, [refreshUsers, refreshAgents]);

  useEffect(() => {
    void refreshAll();
    authApi
      .me()
      .then((u) => setCurrentUserId(u.id))
      .catch(() => setCurrentUserId(null));
  }, [refreshAll]);

  const onCreate = async (values: CreateValues) => {
    setSubmitting(true);
    try {
      await request("/users", {
        method: "POST",
        body: JSON.stringify({
          username: values.username,
          display_name: values.display_name?.trim() || null,
          password: values.password,
          role: values.role,
        }),
      });
      message.success(
        t("adminUsers.createSuccess", { username: values.username }),
      );
      form.resetFields();
      setCreateOpen(false);
      void refreshUsers();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.createFailed"),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const togglePatch = async (
    row: UserRow,
    patch: Partial<Pick<UserRow, "role" | "disabled">>,
  ) => {
    if (
      patch.role === "user" &&
      row.id === currentUserId &&
      row.role === "admin"
    ) {
      message.warning(t("adminUsers.demoteSelf"));
      return;
    }
    try {
      await request(`/users/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      void refreshUsers();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.updateFailed"),
      );
    }
  };

  const onDelete = async (row: UserRow) => {
    try {
      await request(`/users/${row.id}`, { method: "DELETE" });
      message.success(t("adminUsers.deleteSuccess"));
      void refreshAll();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.deleteFailed"),
      );
    }
  };

  const onResetSubmit = async (values: ResetValues) => {
    if (!resetTarget) return;
    setResetSubmitting(true);
    try {
      await request(`/users/${resetTarget.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: values.password }),
      });
      message.success(t("adminUsers.resetSuccess"));
      setResetTarget(null);
      resetForm.resetFields();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.resetFailed"),
      );
    } finally {
      setResetSubmitting(false);
    }
  };

  const onUnlockLogin = async (row: UserRow) => {
    try {
      await request(`/users/${row.id}/unlock-login`, { method: "POST" });
      message.success(t("adminUsers.unlockLoginSuccess"));
      void refreshUsers();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.unlockLoginFailed"),
      );
    }
  };

  return (
    <PageShell
      title={t("pageShell.adminUsers.title")}
      subtitle={t("pageShell.adminUsers.subtitle")}
    >
      <div className={expertStyles.gridToolbar} style={{ marginBottom: 16 }}>
        <span className={expertStyles.gridCount}>
          {t("adminUsers.totalUsers", { count: rows.length })}
        </span>
        <div className={expertStyles.gridToolbarRight}>
          <Segmented
            size="small"
            value={viewMode}
            onChange={(v) => setViewMode(v as "table" | "card")}
            options={[
              {
                value: "card",
                label: (
                  <span className={expertStyles.viewModeLabel}>
                    <LayoutGrid size={14} />
                    {t("adminUsers.viewCard", "卡片")}
                  </span>
                ),
              },
              {
                value: "table",
                label: (
                  <span className={expertStyles.viewModeLabel}>
                    <List size={14} />
                    {t("adminUsers.viewTable", "表格")}
                  </span>
                ),
              },
            ]}
          />
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void refreshAll()}
          >
            {t("common.refresh")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            onClick={() => setCreateOpen(true)}
          >
            {t("adminUsers.newUser")}
          </Button>
        </div>
      </div>

      {showCardView ? (
        <UserCardGrid
          rows={rows}
          loading={loading}
          agentsByUserId={agentsByUserId}
          agentsLoading={agentsLoading}
          currentUserId={currentUserId}
          roleOptions={roleOptions}
          onTogglePatch={togglePatch}
          onShowAgents={setAgentDrawerUser}
          onResetPassword={(row) => {
            setResetTarget(row);
            resetForm.resetFields();
          }}
          onDelete={onDelete}
          onUnlockLogin={onUnlockLogin}
          nowSec={nowSec}
          isSelfAdmin={isSelfAdmin}
        />
      ) : (
        <Table<UserRow>
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={false}
          scroll={{ x: "max-content" }}
          columns={[
            { title: t("adminUsers.colId"), dataIndex: "id", width: 60 },
            { title: t("adminUsers.colUsername"), dataIndex: "username" },
            {
              title: t("adminUsers.colDisplayName"),
              dataIndex: "display_name",
            },
            {
              title: t("adminUsers.colCreatedAt"),
              dataIndex: "created_at",
              width: 168,
              render: (ts: number | undefined) => (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {formatUserTs(ts, timeZone)}
                </Text>
              ),
            },
            {
              title: t("adminUsers.colAgents"),
              width: 96,
              render: (_, row) => {
                const count = agentsByUserId.get(row.id)?.length ?? 0;
                return (
                  <Button
                    type="link"
                    size="small"
                    icon={<Bot size={14} />}
                    onClick={() => setAgentDrawerUser(row)}
                  >
                    {agentsLoading ? "…" : count}
                  </Button>
                );
              },
            },
            {
              title: t("adminUsers.colRole"),
              render: (_, row) => (
                <Tooltip
                  title={
                    isSelfAdmin(row) ? t("adminUsers.demoteSelf") : undefined
                  }
                >
                  <Select
                    size="small"
                    value={row.role}
                    style={{ width: 96 }}
                    options={roleOptions}
                    disabled={isSelfAdmin(row)}
                    onChange={(v) => togglePatch(row, { role: v })}
                  />
                </Tooltip>
              ),
            },
            {
              title: t("common.enabled"),
              render: (_, row) => (
                <Switch
                  size="small"
                  checked={!row.disabled}
                  onChange={(checked) =>
                    togglePatch(row, { disabled: !checked })
                  }
                />
              ),
            },
            {
              title: t("adminUsers.colLoginLock"),
              width: 200,
              render: (_, row) => (
                <UserLoginLock
                  row={row}
                  nowSec={nowSec}
                  onUnlock={() => void onUnlockLogin(row)}
                />
              ),
            },
            {
              title: t("adminUsers.colActions"),
              render: (_, row) => (
                <Space size={4}>
                  <Button
                    size="small"
                    onClick={() => {
                      setResetTarget(row);
                      resetForm.resetFields();
                    }}
                  >
                    {t("adminUsers.resetPassword")}
                  </Button>
                  <Popconfirm
                    title={t("adminUsers.deleteConfirm", {
                      username: row.username,
                    })}
                    onConfirm={() => onDelete(row)}
                    disabled={row.id === currentUserId}
                  >
                    <Tooltip
                      title={
                        row.id === currentUserId
                          ? t("adminUsers.deleteSelf")
                          : undefined
                      }
                    >
                      <Button
                        danger
                        size="small"
                        type="link"
                        disabled={row.id === currentUserId}
                      >
                        {t("common.delete")}
                      </Button>
                    </Tooltip>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      )}

      <Drawer
        title={
          agentDrawerUser
            ? t("adminUsers.agentsDrawerTitle", {
                username: agentDrawerUser.username,
              })
            : ""
        }
        open={agentDrawerUser !== null}
        onClose={() => setAgentDrawerUser(null)}
        width={400}
        destroyOnClose
      >
        <Spin spinning={agentsLoading}>
          {drawerAgents.length === 0 ? (
            <Empty description={t("adminUsers.noAgents")} />
          ) : (
            <div
              className={expertStyles.cardGrid}
              style={{
                gridTemplateColumns: "1fr",
                padding: "8px 0 24px",
              }}
            >
              {drawerAgents.map((agent) => (
                <AgentCard
                  key={agent.agent_id}
                  agent={agent}
                  iconName={agent.icon_name}
                  accentColor={agent.color}
                  onEdit={(id) =>
                    setEditAgent(
                      drawerAgents.find((a) => a.agent_id === id) ?? null,
                    )
                  }
                  onDeleted={handleDrawerDeleted}
                  onStateChange={handleDrawerStateChange}
                  onPollSettled={() => void refreshAgents()}
                />
              ))}
            </div>
          )}
        </Spin>
      </Drawer>

      <EditAgentDrawer
        open={editAgent !== null}
        agent={editAgent}
        onClose={() => setEditAgent(null)}
        onSaved={handleEditSaved}
      />

      <Modal
        title={t("adminUsers.modalNewTitle")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText={t("common.create")}
        cancelText={t("common.cancel")}
        confirmLoading={submitting}
      >
        <Form<CreateValues>
          form={form}
          layout="vertical"
          onFinish={onCreate}
          initialValues={{ role: "user" }}
        >
          <Form.Item
            label={t("adminUsers.formUsername")}
            name="username"
            rules={[
              { required: true },
              {
                pattern: /^[a-zA-Z0-9_-]{1,64}$/,
                message: t("wizard.admin.usernameRule"),
              },
            ]}
          >
            <Input prefix={<User size={16} />} autoFocus />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.formDisplayName")}
            name="display_name"
          >
            <Input prefix={<IdCard size={16} />} />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.formPassword")}
            name="password"
            rules={[{ required: true }]}
          >
            <Input.Password
              prefix={<Lock size={16} />}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.formPasswordConfirm")}
            name="confirm"
            dependencies={["password"]}
            rules={[
              { required: true, message: t("adminUsers.formPasswordConfirm") },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("password") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(
                    new Error(t("wizard.admin.passwordMismatch")),
                  );
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<Lock size={16} />}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.formRole")}
            name="role"
            rules={[{ required: true }]}
          >
            <div className={styles.formSelectAffix}>
              <Shield size={16} className={styles.formSelectAffixIcon} />
              <Select
                className={styles.formSelectAffixControl}
                variant="borderless"
                options={roleOptions}
              />
            </div>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          resetTarget
            ? t("adminUsers.modalResetTitle", {
                username: resetTarget.username,
              })
            : ""
        }
        open={resetTarget !== null}
        onCancel={() => {
          setResetTarget(null);
          resetForm.resetFields();
        }}
        onOk={() => resetForm.submit()}
        okText={t("common.reset")}
        cancelText={t("common.cancel")}
        confirmLoading={resetSubmitting}
      >
        <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
          {t("adminUsers.resetHint")}
        </Text>
        <Form<ResetValues>
          form={resetForm}
          layout="vertical"
          onFinish={onResetSubmit}
        >
          <Form.Item
            label={t("adminUsers.newPassword")}
            name="password"
            rules={[
              { required: true, message: t("adminUsers.newPasswordRequired") },
            ]}
          >
            <Input.Password
              autoComplete="new-password"
              prefix={
                <Lock size={14} style={{ color: "var(--fn-text-tertiary)" }} />
              }
            />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.formPasswordConfirm")}
            name="confirm"
            dependencies={["password"]}
            rules={[
              { required: true, message: t("adminUsers.formPasswordConfirm") },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("password") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(
                    new Error(t("wizard.admin.passwordMismatch")),
                  );
                },
              }),
            ]}
          >
            <Input.Password
              autoComplete="new-password"
              prefix={
                <LockOpen
                  size={14}
                  style={{ color: "var(--fn-text-tertiary)" }}
                />
              }
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
