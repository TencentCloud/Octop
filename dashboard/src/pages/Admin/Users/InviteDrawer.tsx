import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Pagination,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from "antd";
import { Copy, Link2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  SEEDED_USER_ROLE_ID,
  snapshotRoleLabel,
  userRoleLabel,
  userRolesApi,
  type UserRole,
} from "../../../api/modules/userRoles";
import { RoleSelectLabel } from "./ProfileAvatar";
import {
  invitesApi,
  localInviteUrl,
  type InviteRow,
  type InviteStatus,
  type InviteUsersResponse,
} from "../../../api/modules/invites";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage, parseApiError } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./index.module.less";

const { Text } = Typography;

const PAGE_SIZE = 5;
const MAX_INVITE_USES = 2_147_483_647;
const DEFAULT_INVITE_FIELDS = { expires_in_days: 7, max_uses: 1 };

const STATUS_COLOR: Record<InviteStatus, string> = {
  active: "processing",
  disabled: "warning",
  expired: "default",
};

interface InviteDrawerProps {
  open: boolean;
  onClose: () => void;
}

interface InviteFormValues {
  note?: string;
  expires_in_days: number;
  max_uses: number;
  role?: string;
}

function presetInviteRoleId(
  loaded: UserRole[],
  actorIsAdmin: boolean,
): string | undefined {
  const pool = actorIsAdmin
    ? loaded
    : loaded.filter((role) => role.system_role !== "admin");
  return pool.find((role) => role.user_role_id === SEEDED_USER_ROLE_ID)
    ?.user_role_id;
}

export default function InviteDrawer({ open, onClose }: InviteDrawerProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const currentUser = useCurrentUser();
  const actorIsAdmin = currentUser?.role === "admin";
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [rows, setRows] = useState<InviteRow[]>([]);
  const [page, setPage] = useState(1);
  const [roles, setRoles] = useState<UserRole[]>([]);
  const [selectedInvite, setSelectedInvite] = useState<InviteRow | null>(null);
  const [inviteUsers, setInviteUsers] = useState<InviteUsersResponse | null>(
    null,
  );
  const [usersLoading, setUsersLoading] = useState(false);
  const usersRequest = useRef(0);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [form] = Form.useForm<InviteFormValues>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await invitesApi.list());
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminUsers.inviteLoadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!open) return;
    setPage(1);
    form.setFieldsValue({
      ...DEFAULT_INVITE_FIELDS,
      note: undefined,
      role: undefined,
    });
    void refresh();
    void userRolesApi
      .list()
      .then((loaded) => {
        setRoles(loaded);
        form.setFieldValue("role", presetInviteRoleId(loaded, actorIsAdmin));
      })
      .catch((err) => {
        setRoles([]);
        message.error(apiErrorMessage(err, t("adminUsers.roleLoadFailed"), t));
      });
  }, [actorIsAdmin, open, form, refresh, t]);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE) || 1);
  const safePage = Math.min(page, pageCount);
  const pagedRows = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }, [rows, safePage]);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  const onCreate = async (values: InviteFormValues) => {
    setCreating(true);
    try {
      const row = await invitesApi.create({
        note: values.note?.trim() || null,
        expires_in_days: values.expires_in_days,
        max_uses: values.max_uses,
        role: values.role,
      });
      message.success(t("adminUsers.inviteCreateSuccess"));
      form.setFieldsValue({
        ...DEFAULT_INVITE_FIELDS,
        note: undefined,
        role: presetInviteRoleId(roles, actorIsAdmin),
      });
      setRows((prev) => [row, ...prev.filter((r) => r.id !== row.id)]);
      setPage(1);
      const url = localInviteUrl(row.code);
      const ok = await copyText(url);
      if (ok) {
        message.success(t("adminUsers.inviteCopied"));
      }
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("adminUsers.inviteCreateFailed"), t),
      );
    } finally {
      setCreating(false);
    }
  };

  const onCopy = async (row: InviteRow) => {
    const url = localInviteUrl(row.code);
    const ok = await copyText(url);
    if (ok) message.success(t("adminUsers.inviteCopied"));
    else message.error(t("adminUsers.inviteCopyFailed"));
  };

  const onToggle = async (row: InviteRow, enabled: boolean) => {
    setUpdatingId(row.id);
    try {
      const updated = await invitesApi.setEnabled(row.id, enabled);
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("adminUsers.inviteToggleFailed"), t),
      );
      if (parseApiError(err)?.code === "INVITE_EXHAUSTED") void refresh();
    } finally {
      setUpdatingId(null);
    }
  };

  const loadUsers = async (row: InviteRow, page = 1) => {
    const request = ++usersRequest.current;
    setUsersLoading(true);
    try {
      const result = await invitesApi.users(row.id, page);
      if (request === usersRequest.current) setInviteUsers(result);
    } catch (err) {
      if (request === usersRequest.current) {
        message.error(
          apiErrorMessage(err, t("adminUsers.inviteUsersLoadFailed"), t),
        );
      }
    } finally {
      if (request === usersRequest.current) setUsersLoading(false);
    }
  };

  const showUsers = (row: InviteRow) => {
    setSelectedInvite(row);
    setInviteUsers(null);
    void loadUsers(row);
  };

  return (
    <Drawer
      title={t("adminUsers.inviteDrawerTitle")}
      placement="right"
      open={open}
      onClose={onClose}
      width={Math.min(
        560,
        typeof window !== "undefined" ? window.innerWidth - 24 : 560,
      )}
      destroyOnHidden
      className={styles.inviteDrawer}
      styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <Form<InviteFormValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(v) => void onCreate(v)}
        initialValues={DEFAULT_INVITE_FIELDS}
        className={styles.inviteCreateForm}
      >
        <Form.Item
          name="role"
          label={t("adminUsers.inviteRole")}
          extra={t("adminUsers.inviteRoleHint")}
          rules={[
            { required: true, message: t("adminUsers.inviteRoleRequired") },
          ]}
        >
          <Select
            options={(actorIsAdmin
              ? roles
              : roles.filter((role) => role.system_role !== "admin")
            ).map((role) => ({
              value: role.user_role_id,
              label: userRoleLabel(role, t),
            }))}
            optionRender={(option) => {
              const role = roles.find(
                (item) => item.user_role_id === option.value,
              );
              if (!role) return option.label;
              return (
                <RoleSelectLabel
                  url={role.avatar_url}
                  icon={role.avatar_icon}
                  label={userRoleLabel(role, t)}
                />
              );
            }}
            labelRender={(option) => {
              const role = roles.find(
                (item) => item.user_role_id === option.value,
              );
              if (!role) return option.label;
              return (
                <RoleSelectLabel
                  url={role.avatar_url}
                  icon={role.avatar_icon}
                  label={userRoleLabel(role, t)}
                />
              );
            }}
            placeholder={t("adminUsers.inviteRoleRequired")}
          />
        </Form.Item>
        <Form.Item
          name="note"
          label={t("adminUsers.inviteNote")}
          extra={t("adminUsers.inviteNoteHint")}
        >
          <Input
            maxLength={200}
            placeholder={t("adminUsers.inviteNotePlaceholder")}
            allowClear
          />
        </Form.Item>
        <Form.Item
          name="expires_in_days"
          label={t("adminUsers.inviteExpiresDays")}
          rules={[
            {
              required: true,
              message: t("adminUsers.inviteExpiresDaysRequired"),
            },
          ]}
        >
          <InputNumber min={1} max={90} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name="max_uses"
          label={t("adminUsers.inviteMaxUses")}
          extra={t("adminUsers.inviteMaxUsesHint")}
          rules={[
            {
              required: true,
              type: "integer",
              min: 1,
              max: MAX_INVITE_USES,
              message: t("adminUsers.inviteMaxUsesInvalid", {
                max: MAX_INVITE_USES,
              }),
            },
          ]}
        >
          <InputNumber
            min={1}
            max={MAX_INVITE_USES}
            precision={0}
            style={{ width: "100%" }}
          />
        </Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          icon={<Plus size={14} />}
          loading={creating}
          block
        >
          {t("adminUsers.inviteCreate")}
        </Button>
      </Form>

      <div className={styles.inviteListHeader}>
        <Text strong>{t("adminUsers.inviteListTitle")}</Text>
        <Button type="link" size="small" onClick={() => void refresh()}>
          {t("common.refresh")}
        </Button>
      </div>

      {loading ? (
        <div className={styles.inviteLoading}>
          <Spin />
        </div>
      ) : rows.length === 0 ? (
        <Empty description={t("adminUsers.inviteEmpty")} />
      ) : (
        <>
          <div className={styles.inviteList}>
            {pagedRows.map((row) => {
              const limitReached =
                row.max_uses !== null && row.use_count >= row.max_uses;
              const matchedRole = roles.find(
                (role) =>
                  role.user_role_id === row.role ||
                  (!row.role && role.user_role_name === row.role_name),
              );
              return (
                <div key={row.id} className={styles.inviteCard}>
                  <div className={styles.inviteCardTop}>
                    <Space size={8} wrap>
                      <Tag color={STATUS_COLOR[row.status]}>
                        {limitReached && row.status === "disabled"
                          ? t("adminUsers.inviteLimitReached")
                          : t(`adminUsers.inviteStatus.${row.status}`)}
                      </Tag>
                      <Text code>{row.code}</Text>
                    </Space>
                    <Space size={4}>
                      <Button
                        type="text"
                        size="small"
                        icon={<Copy size={14} />}
                        onClick={() => void onCopy(row)}
                        title={t("adminUsers.inviteCopyUrl")}
                      />
                      <Switch
                        size="small"
                        checked={row.enabled}
                        loading={updatingId === row.id}
                        disabled={updatingId !== null || limitReached}
                        onChange={(enabled) => void onToggle(row, enabled)}
                        aria-label={t("adminUsers.inviteEnabled")}
                      />
                    </Space>
                  </div>
                  <div className={styles.inviteUrlRow}>
                    <Link2 size={12} />
                    <Text
                      ellipsis
                      className={styles.inviteUrl}
                      title={localInviteUrl(row.code)}
                    >
                      {localInviteUrl(row.code)}
                    </Text>
                  </div>
                  <Text type="secondary" className={styles.inviteNote}>
                    {row.role_name?.trim() ? (
                      <RoleSelectLabel
                        url={matchedRole?.avatar_url}
                        icon={matchedRole?.avatar_icon}
                        label={snapshotRoleLabel(
                          row.role_name,
                          roles,
                          t,
                          row.role,
                        )}
                      />
                    ) : (
                      t("adminUsers.inviteRoleLegacy")
                    )}
                    {row.role_name?.trim() && !matchedRole ? (
                      <>
                        {" "}
                        <Tag>{t("adminUsers.roleNameMissing")}</Tag>
                      </>
                    ) : null}
                    {row.note ? ` · ${row.note}` : ""}
                  </Text>
                  <Button
                    type="link"
                    size="small"
                    style={{ paddingInline: 0, borderInlineWidth: 0 }}
                    onClick={() => showUsers(row)}
                  >
                    {row.max_uses === null
                      ? t("adminUsers.inviteUsersCount", {
                          count: row.use_count,
                        })
                      : t("adminUsers.inviteUsersCountWithLimit", {
                          count: row.use_count,
                          max: row.max_uses,
                        })}
                  </Button>
                  <div className={styles.inviteMeta}>
                    <Text type="secondary">
                      {t("adminUsers.inviteCreatedAt", {
                        time: formatServerDateTime(row.created_at, timeZone),
                      })}
                    </Text>
                    <Text type="secondary">
                      {t("adminUsers.inviteExpiresAt", {
                        time: formatServerDateTime(row.expires_at, timeZone),
                      })}
                    </Text>
                  </div>
                </div>
              );
            })}
          </div>
          {rows.length > PAGE_SIZE ? (
            <div className={styles.invitePagination}>
              <Pagination
                size="small"
                current={safePage}
                pageSize={PAGE_SIZE}
                total={rows.length}
                onChange={setPage}
                showSizeChanger={false}
              />
            </div>
          ) : null}
        </>
      )}
      <Modal
        title={t("adminUsers.inviteRegisteredUsers", {
          code: selectedInvite?.code,
        })}
        open={selectedInvite !== null}
        onCancel={() => {
          usersRequest.current += 1;
          setSelectedInvite(null);
        }}
        footer={null}
        destroyOnHidden
      >
        {usersLoading ? (
          <Spin />
        ) : !inviteUsers?.users.length ? (
          <Empty description={t("adminUsers.inviteNoUsers")} />
        ) : (
          <>
            {inviteUsers.users.map((user) => (
              <div key={user.id}>
                <Text>{user.display_name || user.username}</Text>
                {user.display_name ? (
                  <Text type="secondary"> ({user.username})</Text>
                ) : null}
                <Text type="secondary">
                  {" "}
                  · {formatServerDateTime(user.redeemed_at, timeZone)}
                </Text>
              </div>
            ))}
            {inviteUsers.total > inviteUsers.page_size ? (
              <Pagination
                current={inviteUsers.page}
                pageSize={inviteUsers.page_size}
                total={inviteUsers.total}
                onChange={(page) =>
                  selectedInvite && void loadUsers(selectedInvite, page)
                }
                showSizeChanger={false}
              />
            ) : null}
          </>
        )}
      </Modal>
    </Drawer>
  );
}
