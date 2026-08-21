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
  Space,
  Popconfirm,
  Switch,
  Typography,
  Tooltip,
  Drawer,
  Empty,
  Spin,
  Tag,
  Segmented,
  Checkbox,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  Bot,
  Check,
  ChevronRight,
  CircleHelp,
  Clock,
  IdCard,
  KeyRound,
  LayoutGrid,
  List,
  Lock,
  LockOpen,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  User,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";
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
  email?: string | null;
  has_password?: boolean;
  sso_linked?: boolean;
  disabled: boolean;
  login_failed_count?: number;
  login_locked?: boolean;
  login_locked_until?: number;
  login_retry_after_seconds?: number;
  created_at?: number;
  permissions?: string[];
}

interface PermissionCatalogItem {
  key: string;
  category: string;
  label: string;
  page?: string;
  page_label?: string;
}

function permFullLabel(item: PermissionCatalogItem): string {
  if (item.page_label) return `${item.page_label} / ${item.label}`;
  return item.label;
}

interface CreateValues {
  username: string;
  display_name?: string;
  password: string;
  confirm: string;
  role: "admin" | "user";
  permissions?: string[];
}

interface EditValues {
  display_name?: string;
  role: "admin" | "user";
  permissions?: string[];
}

interface ResetValues {
  password: string;
  confirm: string;
}

function roleToneClass(role: "admin" | "user"): string {
  return role === "admin" ? styles.roleToneAdmin : styles.roleToneUser;
}

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
  permLabelByKey: Map<string, string>;
  onTogglePatch: (
    row: UserRow,
    patch: Partial<Pick<UserRow, "role" | "disabled" | "permissions">>,
  ) => Promise<boolean>;
  onEdit: (row: UserRow) => void;
  onShowAgents: (row: UserRow) => void;
  onResetPassword: (row: UserRow) => void;
  onDelete: (row: UserRow) => Promise<void>;
  onUnlockLogin: (row: UserRow) => Promise<void>;
  nowSec: number;
}

function userInitials(displayName: string, username: string): string {
  const source = displayName.trim() || username;
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

const FIELD_ICON_PROPS = {
  size: 16 as const,
  style: { color: "var(--fn-text-tertiary)" },
};

interface RolePickerProps {
  value?: "admin" | "user";
  onChange?: (value: "admin" | "user") => void;
  disabled?: boolean;
  options: {
    value: "admin" | "user";
    label: string;
    hint: string;
  }[];
}

function RolePicker({ value, onChange, options, disabled }: RolePickerProps) {
  return (
    <div className={styles.rolePicker} role="radiogroup">
      {options.map((opt) => {
        const selected = value === opt.value;
        const Icon = opt.value === "admin" ? ShieldCheck : UserRound;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            className={`${styles.roleOption} ${
              selected ? styles.roleOptionSelected : ""
            }`}
            onClick={() => {
              if (!disabled) onChange?.(opt.value);
            }}
          >
            <span className={styles.roleOptionIcon} aria-hidden>
              <Icon size={15} strokeWidth={2} />
            </span>
            <span className={styles.roleOptionBody}>
              <span className={styles.roleOptionLabel}>{opt.label}</span>
              <span className={styles.roleOptionHint}>{opt.hint}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface PermissionCheckboxPickerProps {
  value?: string[];
  onChange?: (value: string[]) => void;
  catalog: PermissionCatalogItem[];
  disabled?: boolean;
}

function PermissionCheckboxPicker({
  value,
  onChange,
  catalog,
  disabled,
}: PermissionCheckboxPickerProps) {
  const { t } = useTranslation();
  const selected = value ?? [];
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const groups = useMemo(() => {
    const order = [
      {
        category: "settings",
        label: t("adminUsers.permGroupSettings"),
      },
      {
        category: "control",
        label: t("adminUsers.permGroupControl"),
      },
      {
        category: "admin",
        label: t("adminUsers.permGroupAdmin"),
      },
    ] as const;
    return order
      .map((g) => {
        const items = catalog.filter((p) => p.category === g.category);
        const pages: {
          page: string;
          label: string;
          items: PermissionCatalogItem[];
        }[] = [];
        const standalone: PermissionCatalogItem[] = [];
        for (const item of items) {
          if (!item.page) {
            standalone.push(item);
            continue;
          }
          const existing = pages.find((p) => p.page === item.page);
          if (existing) {
            existing.items.push(item);
          } else {
            pages.push({
              page: item.page,
              label: item.page_label || item.page,
              items: [item],
            });
          }
        }
        return { ...g, items, standalone, pages };
      })
      .filter((g) => g.items.length > 0);
  }, [catalog, t]);

  const toggle = (key: string, checked: boolean) => {
    if (disabled) return;
    if (checked) {
      onChange?.([...selected, key]);
      return;
    }
    onChange?.(selected.filter((k) => k !== key));
  };

  const setGroup = (keys: string[], checked: boolean) => {
    if (disabled) return;
    if (checked) {
      const next = new Set(selected);
      for (const k of keys) next.add(k);
      onChange?.(Array.from(next));
      return;
    }
    const drop = new Set(keys);
    onChange?.(selected.filter((k) => !drop.has(k)));
  };

  if (catalog.length === 0) {
    return (
      <div className={styles.permEmpty}>
        <Text type="secondary">{t("adminUsers.permCatalogEmpty")}</Text>
      </div>
    );
  }

  return (
    <div
      className={`${styles.permPicker} ${
        disabled ? styles.permPickerDisabled : ""
      }`}
    >
      {groups.map((group) => {
        const keys = group.items.map((i) => i.key);
        const checkedCount = keys.filter((k) => selectedSet.has(k)).length;
        const allChecked = checkedCount === keys.length && keys.length > 0;
        const indeterminate = checkedCount > 0 && !allChecked;
        const renderChips = (items: PermissionCatalogItem[]) => (
          <div className={styles.permGrid} role="group">
            {items.map((item) => {
              const checked = selectedSet.has(item.key);
              return (
                <button
                  key={`${item.key}:${item.label}`}
                  type="button"
                  disabled={disabled}
                  aria-pressed={checked}
                  className={`${styles.permChip} ${
                    checked ? styles.permChipSelected : ""
                  }`}
                  onClick={() => toggle(item.key, !checked)}
                >
                  <span className={styles.permChipCheck} aria-hidden>
                    {checked ? <Check size={12} strokeWidth={2.5} /> : null}
                  </span>
                  <span className={styles.permChipLabel}>{item.label}</span>
                </button>
              );
            })}
          </div>
        );
        return (
          <section key={group.category} className={styles.permGroup}>
            <div className={styles.permGroupHeader}>
              <Checkbox
                checked={allChecked}
                indeterminate={indeterminate}
                disabled={disabled}
                onChange={(e) => setGroup(keys, e.target.checked)}
              >
                <span className={styles.permGroupTitle}>{group.label}</span>
              </Checkbox>
              <span className={styles.permGroupCount}>
                {checkedCount}/{keys.length}
              </span>
            </div>
            {group.pages.length === 0 ? (
              renderChips(group.items)
            ) : (
              <>
                {group.standalone.length > 0
                  ? renderChips(group.standalone)
                  : null}
                {group.pages.map((page) => {
                  const pageKeys = page.items.map((i) => i.key);
                  const pageChecked = pageKeys.filter((k) =>
                    selectedSet.has(k),
                  ).length;
                  const pageAll =
                    pageChecked === pageKeys.length && pageKeys.length > 0;
                  const pageIndeterminate = pageChecked > 0 && !pageAll;
                  return (
                    <div key={page.page} className={styles.permPage}>
                      <div className={styles.permPageHeader}>
                        <Checkbox
                          checked={pageAll}
                          indeterminate={pageIndeterminate}
                          disabled={disabled}
                          onChange={(e) => setGroup(pageKeys, e.target.checked)}
                        >
                          <span className={styles.permPageTitle}>
                            {page.label}
                          </span>
                        </Checkbox>
                        <span className={styles.permGroupCount}>
                          {pageChecked}/{pageKeys.length}
                        </span>
                      </div>
                      {renderChips(page.items)}
                    </div>
                  );
                })}
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}

function PermissionSummary({
  row,
  permLabelByKey,
}: {
  row: UserRow;
  permLabelByKey: Map<string, string>;
}) {
  const { t } = useTranslation();
  if (row.role === "admin") {
    return (
      <span className={`${styles.permBadge} ${styles.permBadgeAll}`}>
        {t("adminUsers.permAll")}
      </span>
    );
  }
  const keys = row.permissions ?? [];
  if (keys.length === 0) {
    return <span className={styles.permBadgeMuted}>—</span>;
  }
  const names = keys.map((key) => permLabelByKey.get(key) ?? key);
  return (
    <Tooltip title={names.join("、")}>
      <span className={styles.permBadge}>
        {t("adminUsers.permCount", { count: keys.length })}
      </span>
    </Tooltip>
  );
}

function RoleLegend() {
  const { t } = useTranslation();
  return (
    <div className={styles.roleLegend} role="note">
      <span className={styles.roleLegendLabel}>
        {t("adminUsers.roleLegendTitle")}
      </span>
      <p className={styles.roleLegendText}>{t("adminUsers.roleLegend")}</p>
    </div>
  );
}

function UserCardGrid({
  rows,
  loading,
  agentsByUserId,
  agentsLoading,
  currentUserId,
  permLabelByKey,
  onTogglePatch,
  onEdit,
  onShowAgents,
  onResetPassword,
  onDelete,
  onUnlockLogin,
  nowSec,
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
        const failedCount = row.login_failed_count ?? 0;
        const accentClass = isLocked
          ? styles.userCardAccentLocked
          : row.disabled
          ? styles.userCardAccentDisabled
          : row.role === "admin"
          ? styles.userCardAccentAdmin
          : styles.userCardAccentUser;
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
            <div className={`${styles.userCardAccent} ${accentClass}`} />

            <div className={styles.userCardInner}>
              <div className={styles.userCardHeader}>
                <div
                  className={`${styles.userCardAvatar} ${roleToneClass(
                    row.role,
                  )}`}
                  aria-hidden="true"
                >
                  {userInitials(displayName, row.username)}
                </div>

                <div className={styles.userCardTitleBlock}>
                  <div className={styles.userCardNameRow}>
                    <span className={styles.userCardName}>{displayName}</span>
                    {isSelf && (
                      <Tag className={styles.userCardYouTag}>
                        {t("adminUsers.you")}
                      </Tag>
                    )}
                  </div>
                  <div className={styles.userCardHandle}>@{row.username}</div>
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

              <div className={styles.userCardMeta}>
                <span
                  className={`${styles.userCardPill} ${roleToneClass(
                    row.role,
                  )}`}
                >
                  {row.role === "admin"
                    ? t("adminUsers.roleAdmin")
                    : t("adminUsers.roleUser")}
                </span>
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
                {row.sso_linked && (
                  <span className={styles.userCardAuth}>
                    {t("adminUsers.ssoBadge")}
                  </span>
                )}
                {row.has_password && (
                  <span className={styles.userCardAuth}>
                    {t("adminUsers.passwordBadge")}
                  </span>
                )}
              </div>

              <div className={styles.userCardInfo}>
                {row.created_at != null && (
                  <Tooltip title={t("adminUsers.colCreatedAt")}>
                    <span className={styles.userCardTime}>
                      <Clock size={11} />
                      <span>{formatUserTs(row.created_at, timeZone)}</span>
                    </span>
                  </Tooltip>
                )}
                <PermissionSummary row={row} permLabelByKey={permLabelByKey} />
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
                <Tooltip title={t("common.edit")} mouseEnterDelay={0.5}>
                  <button
                    type="button"
                    className={styles.userCardIconBtn}
                    onClick={() => onEdit(row)}
                    aria-label={t("common.edit")}
                  >
                    <Pencil size={15} />
                  </button>
                </Tooltip>

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

export default function UsersListPanel() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [agents, setAgents] = useState<OctopAgent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<CreateValues>();
  const [editTarget, setEditTarget] = useState<UserRow | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editForm] = Form.useForm<EditValues>();
  const [resetTarget, setResetTarget] = useState<UserRow | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetForm] = Form.useForm<ResetValues>();
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [agentDrawerUser, setAgentDrawerUser] = useState<UserRow | null>(null);
  const [editAgent, setEditAgent] = useState<OctopAgent | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const { viewMode, setViewMode, showCardView } = useCardTableView("table");
  const [permCatalog, setPermCatalog] = useState<PermissionCatalogItem[]>([]);

  const permLabelByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of permCatalog) {
      map.set(item.key, permFullLabel(item));
    }
    return map;
  }, [permCatalog]);

  const baselinePermissions = useMemo(
    () =>
      permCatalog.filter((p) => p.category === "settings").map((p) => p.key),
    [permCatalog],
  );

  const createRoleOptions = useMemo(
    () => [
      {
        value: "user" as const,
        label: t("adminUsers.roleUser"),
        hint: t("adminUsers.roleUserHint"),
      },
      {
        value: "admin" as const,
        label: t("adminUsers.roleAdmin"),
        hint: t("adminUsers.roleAdminHint"),
      },
    ],
    [t],
  );

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

  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) => {
      const username = row.username.toLowerCase();
      const displayName = (row.display_name ?? "").trim().toLowerCase();
      return username.includes(query) || displayName.includes(query);
    });
  }, [rows, searchQuery]);

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
    request<PermissionCatalogItem[]>("/users/permissions")
      .then(setPermCatalog)
      .catch(() => setPermCatalog([]));
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
          permissions: values.role === "admin" ? [] : values.permissions ?? [],
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

  const openCreate = () => {
    form.setFieldsValue({
      role: "user",
      permissions: [...baselinePermissions],
      username: undefined,
      display_name: undefined,
      password: undefined,
      confirm: undefined,
    });
    setCreateOpen(true);
  };

  const openEdit = (row: UserRow) => {
    setEditTarget(row);
    editForm.setFieldsValue({
      display_name: row.display_name ?? "",
      role: row.role,
      permissions: [...(row.permissions ?? [])],
    });
  };

  const togglePatch = async (
    row: UserRow,
    patch: Partial<Pick<UserRow, "role" | "disabled" | "permissions">>,
  ): Promise<boolean> => {
    if (
      patch.role === "user" &&
      row.id === currentUserId &&
      row.role === "admin"
    ) {
      message.warning(t("adminUsers.demoteSelf"));
      return false;
    }
    try {
      await request(`/users/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      void refreshUsers();
      return true;
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.updateFailed"),
      );
      return false;
    }
  };

  const onEditSubmit = async (values: EditValues) => {
    if (!editTarget) return;
    setEditSubmitting(true);
    try {
      await request(`/users/${editTarget.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: values.display_name?.trim() || null,
          role: values.role,
          permissions: values.role === "admin" ? [] : values.permissions ?? [],
        }),
      });
      setEditTarget(null);
      editForm.resetFields();
      void refreshUsers();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminUsers.updateFailed"),
      );
    } finally {
      setEditSubmitting(false);
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
    <>
      <div className={styles.pageTop}>
        <RoleLegend />
        <div className={expertStyles.gridToolbar}>
          <Input
            allowClear
            prefix={<Search size={14} />}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder={t("adminUsers.searchPlaceholder")}
            className={styles.userSearch}
          />
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
              onClick={openCreate}
            >
              {t("adminUsers.newUser")}
            </Button>
          </div>
        </div>
      </div>

      {showCardView ? (
        <UserCardGrid
          rows={filteredRows}
          loading={loading}
          agentsByUserId={agentsByUserId}
          agentsLoading={agentsLoading}
          currentUserId={currentUserId}
          permLabelByKey={permLabelByKey}
          onTogglePatch={togglePatch}
          onEdit={openEdit}
          onShowAgents={setAgentDrawerUser}
          onResetPassword={(row) => {
            setResetTarget(row);
            resetForm.resetFields();
          }}
          onDelete={onDelete}
          onUnlockLogin={onUnlockLogin}
          nowSec={nowSec}
        />
      ) : (
        <Table<UserRow>
          rowKey="id"
          size="middle"
          className={styles.userTable}
          loading={loading}
          dataSource={filteredRows}
          pagination={false}
          scroll={{ x: 960 }}
          rowClassName={(row) =>
            [
              row.disabled ? styles.userTableRowDisabled : "",
              row.login_locked ? styles.userTableRowLocked : "",
            ]
              .filter(Boolean)
              .join(" ")
          }
          columns={[
            {
              title: t("adminUsers.colUsername"),
              width: 240,
              render: (_, row) => {
                const displayName = row.display_name?.trim() || row.username;
                return (
                  <div className={styles.userCell}>
                    <span
                      className={`${styles.userCellAvatar} ${roleToneClass(
                        row.role,
                      )}`}
                    >
                      {userInitials(displayName, row.username)}
                    </span>
                    <span className={styles.userCellText}>
                      <span className={styles.userCellName}>
                        {displayName}
                        {row.id === currentUserId && (
                          <span className={styles.userCellYou}>
                            {t("adminUsers.you")}
                          </span>
                        )}
                      </span>
                      <span className={styles.userCellHandle}>
                        @{row.username}
                      </span>
                    </span>
                  </div>
                );
              },
            },
            {
              title: t("adminUsers.colAuth"),
              width: 120,
              render: (_, row) => {
                const parts = [
                  row.sso_linked ? t("adminUsers.ssoBadge") : null,
                  row.has_password ? t("adminUsers.passwordBadge") : null,
                ].filter(Boolean);
                return (
                  <span className={styles.userCellMuted}>
                    {parts.length ? parts.join(" · ") : "—"}
                  </span>
                );
              },
            },
            {
              title: t("adminUsers.colAgents"),
              width: 80,
              render: (_, row) => {
                const count = agentsByUserId.get(row.id)?.length ?? 0;
                return (
                  <button
                    type="button"
                    className={styles.userCellLink}
                    onClick={() => setAgentDrawerUser(row)}
                  >
                    <Bot size={13} />
                    {agentsLoading ? "…" : count}
                  </button>
                );
              },
            },
            {
              title: t("adminUsers.colRole"),
              width: 88,
              render: (_, row) => (
                <span
                  className={`${styles.userCardPill} ${roleToneClass(
                    row.role,
                  )}`}
                >
                  {row.role === "admin"
                    ? t("adminUsers.roleAdmin")
                    : t("adminUsers.roleUser")}
                </span>
              ),
            },
            {
              title: t("adminUsers.colPermissions"),
              width: 120,
              render: (_, row) => (
                <PermissionSummary row={row} permLabelByKey={permLabelByKey} />
              ),
            },
            {
              title: t("common.enabled"),
              width: 72,
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
              title: t("adminUsers.colCreatedAt"),
              dataIndex: "created_at",
              width: 156,
              render: (ts: number | undefined) => (
                <span className={styles.userCellMuted}>
                  {formatUserTs(ts, timeZone)}
                </span>
              ),
            },
            {
              title: t("adminUsers.colLoginLock"),
              width: 180,
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
              width: 120,
              render: (_, row) => (
                <Space size={4}>
                  <Tooltip title={t("common.edit")}>
                    <button
                      type="button"
                      className={styles.userCardIconBtn}
                      onClick={() => openEdit(row)}
                      aria-label={t("common.edit")}
                    >
                      <Pencil size={14} />
                    </button>
                  </Tooltip>
                  <Tooltip title={t("adminUsers.resetPassword")}>
                    <button
                      type="button"
                      className={styles.userCardIconBtn}
                      onClick={() => {
                        setResetTarget(row);
                        resetForm.resetFields();
                      }}
                      aria-label={t("adminUsers.resetPassword")}
                    >
                      <KeyRound size={14} />
                    </button>
                  </Tooltip>
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
                          : t("common.delete")
                      }
                    >
                      <button
                        type="button"
                        className={`${styles.userCardIconBtn} ${styles.userCardIconBtnDanger}`}
                        disabled={row.id === currentUserId}
                        aria-label={t("common.delete")}
                      >
                        <Trash2 size={14} />
                      </button>
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
        destroyOnHidden
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
                  iconUrl={agent.icon_url}
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

      <Drawer
        title={t("adminUsers.modalNewTitle")}
        placement="right"
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
          form.resetFields();
        }}
        width={Math.min(
          520,
          typeof window !== "undefined" ? window.innerWidth - 24 : 520,
        )}
        destroyOnHidden
        className={styles.createUserDrawer}
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
        footer={
          <div className={styles.createUserFooter}>
            <Button
              onClick={() => {
                setCreateOpen(false);
                form.resetFields();
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="primary"
              loading={submitting}
              onClick={() => form.submit()}
            >
              {t("common.create")}
            </Button>
          </div>
        }
      >
        <Form<CreateValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={onCreate}
          initialValues={{ role: "user", permissions: [] }}
          className={styles.createUserForm}
        >
          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("adminUsers.createSectionAccount")}
            </div>
            <Form.Item
              label={t("adminUsers.formUsername")}
              name="username"
              rules={[
                { required: true, message: t("adminUsers.formUsername") },
                {
                  pattern: /^[a-zA-Z0-9_-]{1,64}$/,
                  message: t("wizard.admin.usernameRule"),
                },
              ]}
            >
              <Input prefix={<User {...FIELD_ICON_PROPS} />} autoFocus />
            </Form.Item>
            <Form.Item
              label={t("adminUsers.formDisplayName")}
              name="display_name"
            >
              <Input prefix={<IdCard {...FIELD_ICON_PROPS} />} />
            </Form.Item>
            <Form.Item
              label={t("adminUsers.formPassword")}
              name="password"
              rules={[
                { required: true, message: t("adminUsers.formPassword") },
              ]}
            >
              <Input.Password
                prefix={<Lock {...FIELD_ICON_PROPS} />}
                autoComplete="new-password"
              />
            </Form.Item>
            <Form.Item
              label={t("adminUsers.formPasswordConfirm")}
              name="confirm"
              dependencies={["password"]}
              rules={[
                {
                  required: true,
                  message: t("adminUsers.formPasswordConfirm"),
                },
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
                prefix={<LockOpen {...FIELD_ICON_PROPS} />}
                autoComplete="new-password"
              />
            </Form.Item>
          </div>

          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("adminUsers.createSectionAccess")}
            </div>
            <div
              className={`${styles.permAdminHint} ${styles.permSectionHint}`}
            >
              <CircleHelp size={15} strokeWidth={2} />
              <span>{t("adminUsers.permEditHint")}</span>
            </div>
            <Form.Item
              label={t("adminUsers.formRole")}
              name="role"
              rules={[{ required: true }]}
              className={styles.createUserRoleItem}
            >
              <RolePicker options={createRoleOptions} />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) => prev.role !== cur.role}
            >
              {({ getFieldValue }) => {
                const isAdminRole = getFieldValue("role") === "admin";
                if (isAdminRole) {
                  return (
                    <div className={styles.permAdminHint}>
                      <ShieldCheck size={15} strokeWidth={2} />
                      <span>{t("adminUsers.permAllHint")}</span>
                    </div>
                  );
                }
                return (
                  <Form.Item
                    label={t("adminUsers.colPermissions")}
                    name="permissions"
                    className={styles.createUserPermItem}
                  >
                    <PermissionCheckboxPicker catalog={permCatalog} />
                  </Form.Item>
                );
              }}
            </Form.Item>
          </div>
        </Form>
      </Drawer>

      <Drawer
        title={
          editTarget
            ? t("adminUsers.modalEditTitle", {
                username: editTarget.username,
              })
            : t("common.edit")
        }
        placement="right"
        open={editTarget !== null}
        onClose={() => {
          setEditTarget(null);
          editForm.resetFields();
        }}
        width={Math.min(
          520,
          typeof window !== "undefined" ? window.innerWidth - 24 : 520,
        )}
        destroyOnHidden
        className={styles.createUserDrawer}
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
        footer={
          <div className={styles.createUserFooter}>
            <Button
              onClick={() => {
                setEditTarget(null);
                editForm.resetFields();
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="primary"
              loading={editSubmitting}
              onClick={() => editForm.submit()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <Form<EditValues>
          form={editForm}
          layout="vertical"
          requiredMark={false}
          onFinish={onEditSubmit}
          className={styles.createUserForm}
        >
          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("adminUsers.createSectionAccount")}
            </div>
            <Form.Item
              label={t("adminUsers.formDisplayName")}
              name="display_name"
            >
              <Input prefix={<IdCard {...FIELD_ICON_PROPS} />} />
            </Form.Item>
          </div>

          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("adminUsers.createSectionAccess")}
            </div>
            <div
              className={`${styles.permAdminHint} ${styles.permSectionHint}`}
            >
              <CircleHelp size={15} strokeWidth={2} />
              <span>{t("adminUsers.permEditHint")}</span>
            </div>
            <Form.Item
              label={t("adminUsers.formRole")}
              name="role"
              rules={[{ required: true }]}
              className={styles.createUserRoleItem}
              extra={
                editTarget && isSelfAdmin(editTarget)
                  ? t("adminUsers.demoteSelf")
                  : undefined
              }
            >
              <RolePicker
                options={createRoleOptions}
                disabled={Boolean(editTarget && isSelfAdmin(editTarget))}
              />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) => prev.role !== cur.role}
            >
              {({ getFieldValue }) => {
                const isAdminRole = getFieldValue("role") === "admin";
                if (isAdminRole) {
                  return (
                    <div className={styles.permAdminHint}>
                      <ShieldCheck size={15} strokeWidth={2} />
                      <span>{t("adminUsers.permAllHint")}</span>
                    </div>
                  );
                }
                return (
                  <Form.Item
                    label={t("adminUsers.colPermissions")}
                    name="permissions"
                    className={styles.createUserPermItem}
                  >
                    <PermissionCheckboxPicker catalog={permCatalog} />
                  </Form.Item>
                );
              }}
            </Form.Item>
          </div>
        </Form>
      </Drawer>

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
    </>
  );
}
