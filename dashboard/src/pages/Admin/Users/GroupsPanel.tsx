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
  description?: string;
  enabled?: boolean;
  user_ids?: number[];
}

function audienceLabel(
  audience: GroupAccessItem["audience"] | "none" | "missing",
  t: (key: string) => string,
): string {
  if (audience === "all") return t("adminUsers.groupAccessAudienceAll");
  if (audience === "creator") return t("adminUsers.groupAccessAudienceCreator");
  if (audience === "owner") return t("adminUsers.groupAccessAudienceOwner");
  if (audience === "none") return t("adminUsers.groupAccessUnavailable");
  if (audience === "missing") return t("adminUsers.groupAccessMissing");
  return t("adminUsers.groupAccessAudienceGroup");
}

function featureTag(
  key: string,
  audience: GroupAccessSummary["connectors"] | undefined,
  label: string,
): GroupAccessItem | null {
  if (audience !== "all" && audience !== "groups") return null;
  return { key, label, missing: false, audience };
}

function summarizeItems(
  items: GroupAccessItem[],
  t: (key: string) => string,
): string {
  if (items.length === 0) return t("adminUsers.groupAccessNoneYet");
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = item.missing ? "missing" : item.audience;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return ["groups", "all", "creator", "owner", "missing"]
    .filter((key) => counts.has(key))
    .map(
      (key) =>
        `${audienceLabel(
          key as GroupAccessItem["audience"] | "missing",
          t,
        )} ${counts.get(key)}`,
    )
    .join(" · ");
}

function accessTags(
  access: GroupAccessSummary | undefined,
  t: (key: string) => string,
): GroupAccessItem[] {
  if (!access) return [];
  const tags: GroupAccessItem[] = [];
  const connectors = featureTag(
    "connectors",
    access.connectors,
    t("adminUsers.groupAccessConnectors"),
  );
  const storage = featureTag(
    "storage",
    access.storage,
    t("adminUsers.groupAccessStorage"),
  );
  if (connectors) tags.push(connectors);
  if (storage) tags.push(storage);
  tags.push(
    ...access.models,
    ...access.skill_packages,
    ...access.knowledge_bases,
  );
  return tags;
}

function AccessItemTags({ items }: { items: GroupAccessItem[] }) {
  const { t } = useTranslation();
  if (items.length === 0) {
    return (
      <span className={styles.userCellMuted}>
        {t("adminUsers.groupAccessNoneYet")}
      </span>
    );
  }
  return (
    <span className={styles.groupAccessTags}>
      {items.map((tag) => (
        <span
          key={`${tag.key}:${tag.label}`}
          className={
            tag.missing
              ? `${styles.groupAccessTag} ${styles.groupAccessTagMissing}`
              : styles.groupAccessTag
          }
          title={
            tag.missing
              ? t("adminUsers.groupAccessMissing")
              : `${tag.label} · ${audienceLabel(tag.audience, t)}`
          }
        >
          {tag.label}
          <span className={styles.groupAccessAudience}>
            {audienceLabel(tag.missing ? "missing" : tag.audience, t)}
          </span>
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
      value: audienceLabel(access?.connectors ?? "all", t),
    },
    {
      key: "storage",
      label: t("adminUsers.groupAccessStorage"),
      value: audienceLabel(access?.storage ?? "all", t),
    },
    {
      key: "models",
      label: t("adminUsers.groupAccessModels"),
      value: summarizeItems(access?.models ?? [], t),
    },
    {
      key: "packages",
      label: t("adminUsers.groupAccessSkillPackages"),
      value: summarizeItems(access?.skill_packages ?? [], t),
    },
    {
      key: "bases",
      label: t("adminUsers.groupAccessKnowledge"),
      value: summarizeItems(access?.knowledge_bases ?? [], t),
    },
  ];
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
  const connector = featureTag(
    "connectors",
    access?.connectors,
    t("adminUsers.groupAccessConnectorsOn"),
  );
  const storage = featureTag(
    "storage",
    access?.storage,
    t("adminUsers.groupAccessStorageOn"),
  );
  const sections: {
    key: string;
    title: string;
    note?: string;
    items: GroupAccessItem[];
  }[] = [
    {
      key: "connectors",
      title: t("adminUsers.groupAccessConnectors"),
      items: connector ? [connector] : [],
    },
    {
      key: "storage",
      title: t("adminUsers.groupAccessStorage"),
      items: storage ? [storage] : [],
    },
    {
      key: "models",
      title: t("adminUsers.groupAccessModels"),
      items: access?.models ?? [],
    },
    {
      key: "packages",
      title: t("adminUsers.groupAccessSkillPackages"),
      note: t("adminUsers.groupAccessSkillNote"),
      items: access?.skill_packages ?? [],
    },
    {
      key: "bases",
      title: t("adminUsers.groupAccessKnowledge"),
      note: t("adminUsers.groupAccessKnowledgeNote"),
      items: access?.knowledge_bases ?? [],
    },
  ];

  return (
    <section className={styles.groupAccessDetail}>
      <div className={styles.groupAccessDetailTitle}>
        {t("adminUsers.groupAccessTitle")}
      </div>
      <p className={styles.groupAccessHint}>
        {t("adminUsers.groupAccessHint")}
      </p>
      {sections.map((section) => (
        <div key={section.key} className={styles.groupAccessSection}>
          <div className={styles.groupAccessSectionTitle}>{section.title}</div>
          {section.note ? (
            <p className={styles.groupAccessNote}>{section.note}</p>
          ) : null}
          {section.items.length === 0 &&
          (section.key === "connectors" || section.key === "storage") ? (
            <span className={styles.userCellMuted}>
              {t("adminUsers.groupAccessUnavailable")}
            </span>
          ) : (
            <AccessItemTags items={section.items} />
          )}
        </div>
      ))}
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
      const accessText = accessTags(row.access, (key) => t(key))
        .map((item) => item.label)
        .join(" ");
      return [row.name, row.description ?? "", memberText, accessText]
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
      const body = {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        enabled: values.enabled !== false,
      };
      const saved = editing
        ? await userGroupsApi.update(editing.user_group_id, body)
        : await userGroupsApi.create({
            ...body,
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
            <p className={styles.roleLegendText}>
              {t("adminUsers.groupAccessHint")}
            </p>
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
                    <span className={styles.userCardAvatarWrap}>
                      <ProfileAvatar
                        url={row.avatar_url}
                        icon={row.avatar_icon}
                        kind="user"
                        className={styles.roleCardAvatar}
                      />
                      <span
                        className={
                          row.enabled === false
                            ? `${styles.userCardStatusDot} ${styles.userCardStatusDotOff}`
                            : styles.userCardStatusDot
                        }
                      />
                    </span>
                    <div className={styles.roleCardTitle}>
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
                    kind="user"
                    className={styles.userCellAvatar}
                  />
                  <span className={styles.userCellText}>
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
            : t("adminUsers.groupCreate")
        }
        open={open}
        onClose={() => setOpen(false)}
        width={480}
        destroyOnHidden
        extra={
          <Button type="primary" loading={saving} onClick={() => void save()}>
            {t("common.save")}
          </Button>
        }
      >
        <ProfileAvatarPicker
          kind="user"
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
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
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
          >
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
          <Form.Item
            name="enabled"
            label={t("adminUsers.groupEnabled")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
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
            />
          </Form.Item>
        </Form>
        {editing ? <AccessDetail access={editing.access} /> : null}
      </Drawer>
    </>
  );
}
