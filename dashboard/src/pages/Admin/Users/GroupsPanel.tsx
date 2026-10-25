import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Typography,
} from "antd";
import {
  LayoutGrid,
  List,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ResizableTable } from "@/components/ResizableTable";
import { TextAssistBar } from "@/components/TextAssistBar";
import { message } from "@/utils/antdMessage";
import { request } from "../../../api/request";
import {
  userGroupsApi,
  type GroupAccessItem,
  type GroupAccessSummary,
  type UserGroup,
} from "../../../api/modules/userGroups";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { ProfileAvatar, ProfileAvatarPicker } from "./ProfileAvatar";
import styles from "./index.module.less";

interface Account {
  id: number;
  username: string;
  display_name: string | null;
  avatar_url?: string | null;
  avatar_icon?: string | null;
  disabled?: boolean;
}

interface GroupFormValues {
  name: string;
  user_group_id?: string;
  description?: string;
  enabled?: boolean;
  user_ids?: number[];
}

const GROUP_ID_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{1,62}[a-zA-Z0-9]$/;

/** Only resources granted to this group (not “everyone” / private). */
function groupGrantedItems(items: GroupAccessItem[]): GroupAccessItem[] {
  return items.filter((item) => item.audience === "groups" || item.missing);
}

function summarizeLabels(items: GroupAccessItem[]): string | null {
  const granted = groupGrantedItems(items);
  if (granted.length === 0) return null;
  return granted.map((item) => item.label).join(" · ");
}

function accessTags(access: GroupAccessSummary | undefined): GroupAccessItem[] {
  if (!access) return [];
  return [
    ...groupGrantedItems(access.connectors ?? []),
    ...groupGrantedItems(access.storage ?? []),
    ...groupGrantedItems(access.models),
    ...groupGrantedItems(access.plugins ?? []),
    ...groupGrantedItems(access.skill_packages),
    ...groupGrantedItems(access.knowledge_bases),
    ...groupGrantedItems(access.bridges ?? []),
    ...groupGrantedItems(access.experts ?? []),
  ];
}

function AccessItemTags({ items }: { items: GroupAccessItem[] }) {
  const { t } = useTranslation();
  const granted = groupGrantedItems(items);
  if (granted.length === 0) {
    return (
      <span className={styles.userCellMuted}>
        {t("adminUsers.groupAccessNoneYet")}
      </span>
    );
  }
  return (
    <span className={styles.groupAccessTags}>
      {granted.map((tag) => (
        <span
          key={`${tag.key}:${tag.label}`}
          className={
            tag.missing
              ? `${styles.groupAccessTag} ${styles.groupAccessTagMissing}`
              : styles.groupAccessTag
          }
          title={tag.missing ? t("adminUsers.groupAccessMissing") : tag.label}
        >
          {tag.label}
        </span>
      ))}
    </span>
  );
}

function AccessSummary({ access }: { access?: GroupAccessSummary }) {
  const { t } = useTranslation();
  const rows = [
    {
      key: "connectors",
      label: t("adminUsers.groupAccessConnectors"),
      value: summarizeLabels(access?.connectors ?? []),
    },
    {
      key: "storage",
      label: t("adminUsers.groupAccessStorage"),
      value: summarizeLabels(access?.storage ?? []),
    },
    {
      key: "models",
      label: t("adminUsers.groupAccessModels"),
      value: summarizeLabels(access?.models ?? []),
    },
    {
      key: "plugins",
      label: t("adminUsers.groupAccessPlugins"),
      value: summarizeLabels(access?.plugins ?? []),
    },
    {
      key: "packages",
      label: t("adminUsers.groupAccessSkillPackages"),
      value: summarizeLabels(access?.skill_packages ?? []),
    },
    {
      key: "bases",
      label: t("adminUsers.groupAccessKnowledge"),
      value: summarizeLabels(access?.knowledge_bases ?? []),
    },
    {
      key: "bridges",
      label: t("adminUsers.groupAccessBridges"),
      value: summarizeLabels(access?.bridges ?? []),
    },
    {
      key: "experts",
      label: t("adminUsers.groupAccessExperts"),
      value: summarizeLabels(access?.experts ?? []),
    },
  ].filter((row) => row.value);

  if (rows.length === 0) {
    return (
      <span className={styles.userCellMuted}>
        {t("adminUsers.groupAccessEmpty")}
      </span>
    );
  }

  return (
    <ul className={styles.groupAccessSummary}>
      {rows.map((row) => (
        <li key={row.key}>
          <span className={styles.groupAccessSummaryKind}>{row.label}</span>
          <span className={styles.groupAccessSummaryValue}>{row.value}</span>
        </li>
      ))}
    </ul>
  );
}

function AccessDetail({ access }: { access?: GroupAccessSummary }) {
  const { t } = useTranslation();
  const sections: {
    key: string;
    title: string;
    items: GroupAccessItem[];
  }[] = [
    {
      key: "connectors",
      title: t("adminUsers.groupAccessConnectors"),
      items: groupGrantedItems(access?.connectors ?? []),
    },
    {
      key: "storage",
      title: t("adminUsers.groupAccessStorage"),
      items: groupGrantedItems(access?.storage ?? []),
    },
    {
      key: "models",
      title: t("adminUsers.groupAccessModels"),
      items: groupGrantedItems(access?.models ?? []),
    },
    {
      key: "plugins",
      title: t("adminUsers.groupAccessPlugins"),
      items: groupGrantedItems(access?.plugins ?? []),
    },
    {
      key: "packages",
      title: t("adminUsers.groupAccessSkillPackages"),
      items: groupGrantedItems(access?.skill_packages ?? []),
    },
    {
      key: "bases",
      title: t("adminUsers.groupAccessKnowledge"),
      items: groupGrantedItems(access?.knowledge_bases ?? []),
    },
    {
      key: "bridges",
      title: t("adminUsers.groupAccessBridges"),
      items: groupGrantedItems(access?.bridges ?? []),
    },
    {
      key: "experts",
      title: t("adminUsers.groupAccessExperts"),
      items: groupGrantedItems(access?.experts ?? []),
    },
  ].filter((section) => section.items.length > 0);

  return (
    <section className={styles.groupAccessDetail}>
      <div className={styles.groupAccessDetailTitle}>
        {t("adminUsers.groupAccessTitle")}
      </div>
      <p className={styles.groupAccessHint}>
        {t("adminUsers.groupAccessHint")}
      </p>
      {sections.length === 0 ? (
        <p className={styles.groupAccessEmpty}>
          {t("adminUsers.groupAccessEmpty")}
        </p>
      ) : (
        sections.map((section) => (
          <div key={section.key} className={styles.groupAccessSection}>
            <div className={styles.groupAccessSectionTitle}>
              {section.title}
            </div>
            <AccessItemTags items={section.items} />
          </div>
        ))
      )}
    </section>
  );
}

function accountLabel(user: Account): string {
  const name = user.display_name?.trim();
  return name ? `${name} (${user.username})` : user.username;
}

function MemberFaces({
  ids,
  usersById,
}: {
  ids: number[];
  usersById: Map<number, Account>;
}) {
  const { t } = useTranslation();
  const shown = ids.slice(0, 4);
  const extra = ids.length - shown.length;
  if (shown.length === 0) {
    return <span className={styles.userCellMuted}>—</span>;
  }
  return (
    <span className={styles.groupMemberStack}>
      {shown.map((id) => {
        const user = usersById.get(id);
        return (
          <ProfileAvatar
            key={id}
            url={user?.avatar_url}
            icon={user?.avatar_icon}
            kind="user"
            className={styles.groupMemberAvatar}
          />
        );
      })}
      {extra > 0 ? (
        <span className={styles.groupMemberMore}>
          {t("adminUsers.groupMemberMore", { count: extra })}
        </span>
      ) : null}
    </span>
  );
}

export default function GroupsPanel() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const { viewMode, setViewMode, showCardView } = useCardTableView("table");
  const [rows, setRows] = useState<UserGroup[]>([]);
  const [users, setUsers] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<UserGroup | null>(null);
  const [pendingIcon, setPendingIcon] = useState<string | null>(null);
  const [pendingAvatar, setPendingAvatar] = useState<File | null>(null);
  const [form] = Form.useForm<GroupFormValues>();

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [groups, accounts] = await Promise.all([
        userGroupsApi.list(),
        request<Account[]>("/users"),
      ]);
      setRows(groups);
      setUsers(accounts);
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupLoadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => {
      const memberText = (row.member_ids ?? [])
        .map((id) => {
          const user = usersById.get(id);
          return user ? accountLabel(user) : "";
        })
        .join(" ");
      const accessText = accessTags(row.access)
        .map((item) => item.label)
        .join(" ");
      return [
        row.user_group_id,
        row.name,
        row.description ?? "",
        memberText,
        accessText,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [query, rows, t, usersById]);

  const openCreate = () => {
    setEditing(null);
    setPendingIcon(null);
    setPendingAvatar(null);
    form.setFieldsValue({
      name: "",
      user_group_id: "",
      description: "",
      enabled: true,
      user_ids: [],
    });
    setOpen(true);
  };

  const openEdit = async (row: UserGroup) => {
    setEditing(row);
    setPendingIcon(null);
    setPendingAvatar(null);
    form.setFieldsValue({
      name: row.name,
      user_group_id: row.user_group_id,
      description: row.description ?? "",
      enabled: row.enabled !== false,
      user_ids: row.member_ids ?? [],
    });
    setOpen(true);
    try {
      const members = await userGroupsApi.members(row.user_group_id);
      form.setFieldValue("user_ids", members.user_ids);
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupLoadFailed"), t));
    }
  };

  const setEnabled = async (row: UserGroup, enabled: boolean) => {
    try {
      await userGroupsApi.update(row.user_group_id, { enabled });
      setRows((current) =>
        current.map((item) =>
          item.user_group_id === row.user_group_id
            ? { ...item, enabled }
            : item,
        ),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupSaveFailed"), t));
    }
  };

  const save = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const description = values.description?.trim() || "";
      const body = {
        name: values.name.trim(),
        description: description ? description.slice(0, 500) : null,
        enabled: values.enabled !== false,
      };
      const customId = values.user_group_id?.trim() || undefined;
      const saved = editing
        ? await userGroupsApi.update(editing.user_group_id, body)
        : await userGroupsApi.create({
            ...body,
            user_group_id: customId,
            avatar_icon: pendingAvatar ? null : pendingIcon,
          });
      if (!editing && pendingAvatar) {
        await userGroupsApi.uploadAvatar(saved.user_group_id, pendingAvatar);
      }
      await userGroupsApi.replaceMembers(
        saved.user_group_id,
        values.user_ids ?? [],
      );
      setOpen(false);
      message.success(
        t(editing ? "adminUsers.groupUpdated" : "adminUsers.groupCreated"),
      );
      await load();
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupSaveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row: UserGroup) => {
    try {
      await userGroupsApi.remove(row.user_group_id);
      message.success(t("adminUsers.groupDeleted"));
      await load();
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupSaveFailed"), t));
    }
  };

  const emptyText = query.trim()
    ? t("adminUsers.groupNoMatch")
    : t("adminUsers.groupEmpty");

  return (
    <>
      <div className={styles.pageTop}>
        <div className={styles.roleLegend} role="note">
          <span className={styles.roleLegendLabel}>
            {t("adminUsers.tabGroups")}
          </span>
          <div className={styles.roleLegendNotes}>
            <p className={styles.roleLegendText}>{t("adminUsers.groupHint")}</p>
          </div>
        </div>
        <div className={styles.roleToolbar}>
          <div className={styles.userSearchRow}>
            <Input
              allowClear
              prefix={<Search size={14} />}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("adminUsers.groupSearchPlaceholder")}
              className={styles.userSearch}
            />
          </div>
          <Segmented
            size="small"
            value={viewMode}
            onChange={(value) => setViewMode(value as "table" | "card")}
            options={[
              {
                value: "card",
                label: (
                  <span className={styles.roleViewModeLabel}>
                    <LayoutGrid size={14} />
                    {t("adminUsers.viewCard")}
                  </span>
                ),
              },
              {
                value: "table",
                label: (
                  <span className={styles.roleViewModeLabel}>
                    <List size={14} />
                    {t("adminUsers.viewTable")}
                  </span>
                ),
              },
            ]}
          />
          <Button icon={<RefreshCw size={14} />} onClick={() => void load()}>
            {t("common.refresh")}
          </Button>
          <Button type="primary" icon={<Plus size={14} />} onClick={openCreate}>
            {t("adminUsers.groupCreate")}
          </Button>
        </div>
      </div>

      {showCardView ? (
        loading && rows.length === 0 ? (
          <div className={styles.roleCardLoading}>
            <Spin />
          </div>
        ) : filtered.length === 0 ? (
          <Empty description={emptyText} />
        ) : (
          <div className={styles.roleCardGrid}>
            {filtered.map((row) => (
              <article
                key={row.user_group_id}
                className={[
                  styles.roleCard,
                  row.enabled === false ? styles.groupCardOff : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <div className={styles.roleCardBody}>
                  <div className={styles.roleCardTop}>
                    <ProfileAvatar
                      url={row.avatar_url}
                      icon={row.avatar_icon}
                      kind="role"
                      className={styles.roleCardAvatar}
                    />
                    <div className={styles.roleCardTitle}>
                      <span
                        className={styles.roleIdMeta}
                        title={row.user_group_id}
                      >
                        {row.user_group_id}
                      </span>
                      <h3>{row.name}</h3>
                      <span className={styles.roleIdMeta}>
                        {t("adminUsers.groupMemberCount", {
                          count: row.member_count,
                        })}
                        <span className={styles.userCardMetaSep}>·</span>
                        {formatServerDateTime(row.created_at, timeZone)}
                      </span>
                    </div>
                  </div>
                  <p className={styles.roleCardDescription}>
                    {row.description?.trim() || "—"}
                  </p>
                  <AccessSummary access={row.access} />
                  <MemberFaces
                    ids={row.member_ids ?? []}
                    usersById={usersById}
                  />
                </div>
                <div className={styles.roleCardFooter}>
                  <Switch
                    size="small"
                    checked={row.enabled !== false}
                    onChange={(checked) => void setEnabled(row, checked)}
                  />
                  <span className={styles.roleCardFootNote}>
                    {row.enabled === false
                      ? t("adminUsers.statusDisabled")
                      : t("adminUsers.statusEnabled")}
                  </span>
                  <span className={styles.userCardFooterSpacer} />
                  <Button
                    type="text"
                    size="small"
                    icon={<Pencil size={14} />}
                    onClick={() => void openEdit(row)}
                    aria-label={t("common.edit")}
                  />
                  <Popconfirm
                    title={t("adminUsers.groupDeleteConfirm", {
                      name: row.name,
                    })}
                    onConfirm={() => void remove(row)}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<Trash2 size={14} />}
                      aria-label={t("common.delete")}
                    />
                  </Popconfirm>
                </div>
              </article>
            ))}
          </div>
        )
      ) : (
        <ResizableTable
          storageKey="admin-user-groups"
          rowKey="user_group_id"
          size="middle"
          loading={loading}
          dataSource={filtered}
          pagination={false}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={emptyText}
              />
            ),
          }}
          columns={[
            {
              title: t("adminUsers.groupName"),
              dataIndex: "name",
              width: 240,
              render: (_name: string, row: UserGroup) => (
                <div className={styles.userCell}>
                  <ProfileAvatar
                    url={row.avatar_url}
                    icon={row.avatar_icon}
                    kind="role"
                    className={styles.userCellAvatar}
                  />
                  <span className={styles.userCellText}>
                    <span
                      className={styles.roleIdMeta}
                      title={row.user_group_id}
                    >
                      {row.user_group_id}
                    </span>
                    <span className={styles.userCellName}>{row.name}</span>
                  </span>
                </div>
              ),
            },
            {
              title: t("adminUsers.groupDescription"),
              dataIndex: "description",
              ellipsis: true,
              render: (value: string | null) => (
                <span
                  className={styles.userCellMuted}
                  title={value?.trim() || undefined}
                >
                  {value?.trim() || "—"}
                </span>
              ),
            },
            {
              title: t("adminUsers.groupAccessTitle"),
              width: 260,
              render: (_value: unknown, row: UserGroup) => (
                <AccessSummary access={row.access} />
              ),
            },
            {
              title: t("adminUsers.groupMembers"),
              width: 220,
              render: (_value: unknown, row: UserGroup) => (
                <Space size={8}>
                  <MemberFaces
                    ids={row.member_ids ?? []}
                    usersById={usersById}
                  />
                  <span className={styles.userCellMuted}>
                    {t("adminUsers.groupMemberCount", {
                      count: row.member_count,
                    })}
                  </span>
                </Space>
              ),
            },
            {
              title: t("adminUsers.groupEnabled"),
              width: 110,
              render: (_value: unknown, row: UserGroup) => (
                <Switch
                  checked={row.enabled !== false}
                  onChange={(checked) => void setEnabled(row, checked)}
                />
              ),
            },
            {
              title: t("adminUsers.groupColCreated"),
              width: 180,
              render: (_value: unknown, row: UserGroup) => (
                <span className={styles.userCellMuted}>
                  {formatServerDateTime(row.created_at, timeZone)}
                </span>
              ),
            },
            {
              title: "",
              width: 96,
              render: (_value: unknown, row: UserGroup) => (
                <Space>
                  <Button
                    type="text"
                    icon={<Pencil size={16} />}
                    onClick={() => void openEdit(row)}
                    aria-label={t("common.edit")}
                  />
                  <Popconfirm
                    title={t("adminUsers.groupDeleteConfirm", {
                      name: row.name,
                    })}
                    onConfirm={() => void remove(row)}
                  >
                    <Button
                      type="text"
                      danger
                      icon={<Trash2 size={16} />}
                      aria-label={t("common.delete")}
                    />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      )}

      <Drawer
        title={
          editing
            ? t("adminUsers.groupEditTitle", { name: editing.name })
            : t("adminUsers.groupCreateTitle")
        }
        open={open}
        onClose={() => setOpen(false)}
        width={480}
        destroyOnHidden
        className={styles.createUserDrawer}
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
        footer={
          <div className={styles.createUserFooter}>
            <Button onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button type="primary" loading={saving} onClick={() => void save()}>
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <ProfileAvatarPicker
          kind="role"
          avatarUrl={pendingAvatar ? undefined : editing?.avatar_url}
          icon={editing ? editing.avatar_icon : pendingIcon}
          onSelectIcon={async (icon) => {
            if (!editing) {
              setPendingIcon(icon);
              setPendingAvatar(null);
              return;
            }
            const updated = await userGroupsApi.update(editing.user_group_id, {
              avatar_icon: icon,
            });
            if (editing.avatar_url) {
              await userGroupsApi.deleteAvatar(editing.user_group_id);
            }
            setEditing({ ...editing, ...updated, avatar_url: null });
            void load();
          }}
          onPick={async (file) => {
            if (!editing) {
              setPendingAvatar(file);
              setPendingIcon(null);
              return;
            }
            const uploaded = await userGroupsApi.uploadAvatar(
              editing.user_group_id,
              file,
            );
            setEditing({ ...editing, avatar_url: uploaded.avatar_url });
            void load();
          }}
          onRemove={
            editing
              ? async () => {
                  await userGroupsApi.deleteAvatar(editing.user_group_id);
                  setEditing({ ...editing, avatar_url: null });
                  void load();
                }
              : pendingAvatar
              ? () => setPendingAvatar(null)
              : undefined
          }
        />
        <Form
          form={form}
          layout="vertical"
          className={styles.createUserForm}
          style={{ marginTop: 16 }}
        >
          {editing ? (
            <Form.Item label={t("adminUsers.groupColId")}>
              <Typography.Text
                code
                copyable={{ text: editing.user_group_id }}
                className={styles.roleIdField}
              >
                {editing.user_group_id}
              </Typography.Text>
            </Form.Item>
          ) : (
            <Form.Item
              name="user_group_id"
              label={t("adminUsers.groupColId")}
              extra={t("adminUsers.groupIdHint")}
              rules={[
                {
                  validator: (_: unknown, value: string | undefined) => {
                    const id = value?.trim() ?? "";
                    if (!id) return Promise.resolve();
                    if (!GROUP_ID_RE.test(id)) {
                      return Promise.reject(
                        new Error(t("adminUsers.groupIdInvalid")),
                      );
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <Input
                maxLength={64}
                allowClear
                placeholder={t("adminUsers.groupIdPlaceholder")}
              />
            </Form.Item>
          )}
          <Form.Item
            name="name"
            label={t("adminUsers.groupName")}
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={64} autoFocus />
          </Form.Item>
          <Form.Item
            name="description"
            label={t("adminUsers.groupDescription")}
            className={styles.textAssistField}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <TextAssistBar
            kind="user_group.description"
            getName={() => String(form.getFieldValue("name") ?? "")}
            getText={() => String(form.getFieldValue("description") ?? "")}
            onApply={(text) =>
              form.setFieldsValue({ description: text.slice(0, 500) })
            }
          />
          <Form.Item name="user_ids" label={t("adminUsers.groupMembers")}>
            <Select
              mode="multiple"
              optionFilterProp="label"
              options={users.map((user) => ({
                value: user.id,
                label: accountLabel(user),
                disabled: user.disabled,
              }))}
              optionRender={(option) => {
                const user = usersById.get(Number(option.value));
                if (!user) return option.label;
                return (
                  <span className={styles.roleSelectOption}>
                    <ProfileAvatar
                      url={user.avatar_url}
                      icon={user.avatar_icon}
                      kind="user"
                      className={styles.roleSelectIcon}
                    />
                    <span className={styles.roleSelectName}>
                      {accountLabel(user)}
                    </span>
                  </span>
                );
              }}
              labelRender={(option) => {
                const user = usersById.get(Number(option.value));
                if (!user) return option.label;
                return (
                  <span className={styles.roleSelectOption}>
                    <ProfileAvatar
                      url={user.avatar_url}
                      icon={user.avatar_icon}
                      kind="user"
                      className={styles.roleSelectIcon}
                    />
                    <span className={styles.roleSelectName}>
                      {accountLabel(user)}
                    </span>
                  </span>
                );
              }}
            />
          </Form.Item>
          <Form.Item
            name="enabled"
            label={t("adminUsers.groupEnabled")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
        {editing ? <AccessDetail access={editing.access} /> : null}
      </Drawer>
    </>
  );
}
