import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  IdCard,
  LayoutGrid,
  List,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ResizableTable } from "@/components/ResizableTable";
import { TextAssistBar } from "@/components/TextAssistBar";
import { message } from "@/utils/antdMessage";
import {
  userRolesApi,
  userRoleDescription,
  userRoleLabel,
  type UserRole,
} from "../../../api/modules/userRoles";
import { request } from "../../../api/request";
import { apiErrorMessage } from "../../../utils/apiError";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { fetchFilesystemDefaults } from "../../Experts/components/agentBackendForm";
import { HOST_FS_ROOT } from "../../Experts/components/rootDirTree";
import styles from "./index.module.less";
import { ProfileAvatar, ProfileAvatarPicker } from "./ProfileAvatar";
import {
  PermissionCheckboxPicker,
  ResourcePolicyFields,
  rolePoliciesFromForm,
  type PermissionCatalogItem,
  type PolicyFormValues,
} from "./UsersListPanel";

interface RoleFormValues extends PolicyFormValues {
  name: string;
  user_role_id?: string;
  description?: string;
  permissions?: string[];
}

interface RoleAccount {
  id: number;
  role: string;
  username: string;
  display_name: string | null;
  avatar_url?: string | null;
  avatar_icon?: string | null;
}

const ROLE_ID_MAX = 64;

function isValidRoleId(value: string): boolean {
  return (
    value.length >= 1 &&
    value.length <= ROLE_ID_MAX &&
    /^[A-Za-z_]+$/.test(value) &&
    !value.startsWith("_") &&
    !value.endsWith("_")
  );
}

function RoleMemberFaces({
  ids,
  usersById,
}: {
  ids: number[];
  usersById: Map<number, RoleAccount>;
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
          {t("adminUsers.roleMemberMore", { count: extra })}
        </span>
      ) : null}
    </span>
  );
}

export default function RolesPanel() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<UserRole[]>([]);
  const [users, setUsers] = useState<RoleAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [permCatalog, setPermCatalog] = useState<PermissionCatalogItem[]>([]);
  const [fsTreeRoots, setFsTreeRoots] = useState<string[]>([HOST_FS_ROOT]);
  const [workspaceRootAllowed, setWorkspaceRootAllowed] = useState(true);
  const [editor, setEditor] = useState<UserRole | "new" | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<RoleFormValues>();
  const [pendingAvatar, setPendingAvatar] = useState<File | null>(null);
  const [pendingIcon, setPendingIcon] = useState<string | null>(null);
  const { viewMode, setViewMode, showCardView } = useCardTableView("table");

  const baselinePermissions = useMemo(
    () =>
      permCatalog
        .filter(
          (item) => item.category === "settings" || item.category === "nav",
        )
        .map((item) => item.key),
    [permCatalog],
  );

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
  );

  const membersByRole = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const user of users) {
      const roleId = user.role?.trim();
      if (!roleId) continue;
      const list = map.get(roleId);
      if (list) list.push(user.id);
      else map.set(roleId, [user.id]);
    }
    return map;
  }, [users]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [roles, accounts] = await Promise.all([
        userRolesApi.list(),
        request<RoleAccount[]>("/users"),
      ]);
      setRows(roles);
      setUsers(accounts);
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminUsers.roleLoadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
    request<PermissionCatalogItem[]>("/users/permissions")
      .then(setPermCatalog)
      .catch(() => setPermCatalog([]));
    fetchFilesystemDefaults()
      .then((defaults) => {
        setFsTreeRoots(
          defaults.browse_roots?.length
            ? defaults.browse_roots
            : [defaults.tree_root],
        );
        setWorkspaceRootAllowed(!defaults.in_container);
      })
      .catch(() => {
        setFsTreeRoots([HOST_FS_ROOT]);
        setWorkspaceRootAllowed(true);
      });
  }, [refresh]);

  const descriptionForForm = useCallback(
    (row: UserRole) => {
      const stored = row.description?.trim();
      if (stored) return stored;
      if (row.user_role_id === "admin" || row.user_role_id === "user") {
        return userRoleDescription(row, t);
      }
      return "";
    },
    [t],
  );

  const openCreate = () => {
    setPendingAvatar(null);
    setPendingIcon(null);
    setEditor("new");
  };

  const openEdit = (row: UserRole) => {
    setPendingAvatar(null);
    setPendingIcon(null);
    setEditor(row);
  };

  const formInitialValues: RoleFormValues =
    !editor || editor === "new"
      ? {
          name: "",
          user_role_id: "",
          description: "",
          permissions: [...baselinePermissions],
          limit_workspace_root: false,
          limit_token_quota: false,
          limit_max_agents: false,
        }
      : {
          name: editor.user_role_name,
          description: descriptionForForm(editor),
          permissions:
            editor.system_role === "admin" ? [] : [...editor.permissions],
          limit_workspace_root: workspaceRootAllowed
            ? Boolean(editor.workspace_root_dir)
            : false,
          workspace_root_dir: workspaceRootAllowed
            ? editor.workspace_root_dir ?? undefined
            : undefined,
          limit_token_quota: editor.token_quota != null,
          token_quota: editor.token_quota ?? undefined,
          limit_max_agents: editor.max_agents != null,
          max_agents: editor.max_agents ?? undefined,
        };
  const formKey =
    editor === "new" ? "new" : editor ? editor.user_role_id : "closed";
  const editorRef = useRef(editor);
  const formValuesRef = useRef(formInitialValues);
  editorRef.current = editor;
  formValuesRef.current = formInitialValues;

  useLayoutEffect(() => {
    const current = editorRef.current;
    if (!current) return;
    form.setFieldsValue(formValuesRef.current);
  }, [form, formKey]);

  const closeEditor = () => {
    setEditor(null);
    form.resetFields();
  };

  const onSubmit = async (values: RoleFormValues) => {
    const editing = editor !== "new" ? editor : null;
    setSubmitting(true);
    try {
      const descriptionRaw = values.description?.trim() || "";
      const description = descriptionRaw ? descriptionRaw.slice(0, 500) : null;
      if (editing?.immutable) {
        await userRolesApi.update(editing.user_role_id, {
          user_role_name: values.name.trim(),
          description,
        });
        message.success(t("adminUsers.roleUpdateSuccess"));
      } else if (editing) {
        await userRolesApi.update(editing.user_role_id, {
          user_role_name: values.name.trim(),
          description,
          permissions: values.permissions ?? [],
          policies: rolePoliciesFromForm(values, { workspaceRootAllowed }),
        });
        message.success(t("adminUsers.roleUpdateSuccess"));
      } else {
        const created = await userRolesApi.create({
          user_role_id: values.user_role_id?.trim(),
          user_role_name: values.name.trim(),
          description,
          permissions: values.permissions ?? [],
          policies: rolePoliciesFromForm(values, { workspaceRootAllowed }),
        });
        if (pendingAvatar) {
          await userRolesApi.uploadAvatar(created.user_role_id, pendingAvatar);
        } else if (pendingIcon) {
          await userRolesApi.update(created.user_role_id, {
            avatar_icon: pendingIcon,
          });
        }
        message.success(
          t("adminUsers.roleCreateSuccess", { name: values.name.trim() }),
        );
      }
      setPendingAvatar(null);
      setPendingIcon(null);
      closeEditor();
      void refresh();
    } catch (err) {
      message.error(
        apiErrorMessage(
          err,
          editing
            ? t("adminUsers.roleUpdateFailed")
            : t("adminUsers.roleCreateFailed"),
          t,
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (row: UserRole) => {
    try {
      await userRolesApi.remove(row.user_role_id);
      message.success(t("adminUsers.roleDeleteSuccess"));
      void refresh();
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminUsers.roleDeleteFailed"), t));
    }
  };

  const editing = editor !== "new" ? editor : null;
  const locked = Boolean(editing?.immutable);

  return (
    <>
      <div className={styles.pageTop}>
        <div className={styles.roleLegend} role="note">
          <span className={styles.roleLegendLabel}>
            {t("adminUsers.tabRoles")}
          </span>
          <p className={styles.roleLegendText}>
            {t("adminUsers.roleTemplateHint")}
          </p>
        </div>
        <div className={styles.roleToolbar}>
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
          <Button icon={<RefreshCw size={14} />} onClick={() => void refresh()}>
            {t("common.refresh")}
          </Button>
          <Button type="primary" icon={<Plus size={14} />} onClick={openCreate}>
            {t("adminUsers.roleCreate")}
          </Button>
        </div>
      </div>

      {showCardView ? (
        loading && rows.length === 0 ? (
          <div className={styles.roleCardLoading}>
            <Spin />
          </div>
        ) : rows.length === 0 ? (
          <Empty description={t("adminUsers.roleEmpty")} />
        ) : (
          <div className={styles.roleCardGrid}>
            {rows.map((row) => {
              const limited =
                Boolean(row.workspace_root_dir) ||
                row.token_quota != null ||
                row.max_agents != null;
              return (
                <article key={row.user_role_id} className={styles.roleCard}>
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
                          title={row.user_role_id}
                        >
                          {row.user_role_id}
                        </span>
                        <h3>
                          {userRoleLabel(row, t)}
                          {!row.deletable ? (
                            <span className={styles.roleCardBuiltin}>
                              {t("adminUsers.roleBuiltin")}
                            </span>
                          ) : null}
                        </h3>
                      </div>
                    </div>
                    <p className={styles.roleCardDescription}>
                      {userRoleDescription(row, t)}
                    </p>
                    <RoleMemberFaces
                      ids={membersByRole.get(row.user_role_id) ?? []}
                      usersById={usersById}
                    />
                  </div>
                  <div className={styles.roleCardFooter}>
                    <span className={styles.roleCardFootNote}>
                      {t("adminUsers.roleMemberCount", {
                        count: membersByRole.get(row.user_role_id)?.length ?? 0,
                      })}
                      <span className={styles.userCardMetaSep}>·</span>
                      {row.system_role === "admin"
                        ? t("adminUsers.permAll")
                        : t("adminUsers.permCount", {
                            count: row.permissions.length,
                          })}
                      <span className={styles.userCardMetaSep}>·</span>
                      {limited
                        ? t("adminUsers.rolePolicyLimited")
                        : t("adminUsers.rolePolicyUnlimited")}
                    </span>
                    <span className={styles.userCardFooterSpacer} />
                    <Button
                      type="text"
                      size="small"
                      icon={<Pencil size={14} />}
                      onClick={() => openEdit(row)}
                      aria-label={t("common.edit")}
                    />
                    <Popconfirm
                      title={t("adminUsers.roleDeleteConfirm", {
                        name: userRoleLabel(row, t),
                      })}
                      onConfirm={() => void onDelete(row)}
                      disabled={!row.deletable}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        disabled={!row.deletable}
                        icon={<Trash2 size={14} />}
                        aria-label={t("common.delete")}
                      />
                    </Popconfirm>
                  </div>
                </article>
              );
            })}
          </div>
        )
      ) : (
        <ResizableTable
          storageKey="admin-user-roles"
          rowKey="user_role_id"
          size="middle"
          loading={loading}
          dataSource={rows}
          pagination={false}
          locale={{
            emptyText: <Empty description={t("adminUsers.roleEmpty")} />,
          }}
          columns={[
            {
              title: t("adminUsers.roleColName"),
              dataIndex: "user_role_name",
              width: 260,
              render: (_name: string, row) => (
                <div className={styles.userCell}>
                  <ProfileAvatar
                    url={row.avatar_url}
                    icon={row.avatar_icon}
                    kind="role"
                    className={styles.roleCellAvatar}
                  />
                  <span className={styles.userCellText}>
                    <span
                      className={styles.roleIdMeta}
                      title={row.user_role_id}
                    >
                      {row.user_role_id}
                    </span>
                    <span className={styles.userCellName}>
                      {userRoleLabel(row, t)}
                      {!row.deletable ? (
                        <Tag>{t("adminUsers.roleBuiltin")}</Tag>
                      ) : null}
                    </span>
                  </span>
                </div>
              ),
            },
            {
              title: t("adminUsers.roleDescription"),
              dataIndex: "description",
              ellipsis: true,
              render: (_description: string | null, row) =>
                userRoleDescription(row, t),
            },
            {
              title: t("adminUsers.roleMembers"),
              width: 200,
              render: (_, row) => {
                const ids = membersByRole.get(row.user_role_id) ?? [];
                return (
                  <Space size={8}>
                    <RoleMemberFaces ids={ids} usersById={usersById} />
                    <span className={styles.userCellMuted}>
                      {t("adminUsers.roleMemberCount", { count: ids.length })}
                    </span>
                  </Space>
                );
              },
            },
            {
              title: t("adminUsers.colPermissions"),
              width: 160,
              render: (_, row) =>
                row.system_role === "admin"
                  ? t("adminUsers.permAll")
                  : t("adminUsers.permCount", {
                      count: row.permissions.length,
                    }),
            },
            {
              title: t("adminUsers.roleColPolicy"),
              width: 140,
              render: (_, row) => {
                const limited =
                  Boolean(row.workspace_root_dir) ||
                  row.token_quota != null ||
                  row.max_agents != null;
                return limited
                  ? t("adminUsers.rolePolicyLimited")
                  : t("adminUsers.rolePolicyUnlimited");
              },
            },
            {
              title: t("adminUsers.colActions"),
              width: 100,
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
                  <Popconfirm
                    title={t("adminUsers.roleDeleteConfirm", {
                      name: userRoleLabel(row, t),
                    })}
                    onConfirm={() => void onDelete(row)}
                    disabled={!row.deletable}
                  >
                    <Tooltip
                      title={
                        row.deletable
                          ? t("common.delete")
                          : t("adminUsers.roleDeleteBuiltin")
                      }
                    >
                      <button
                        type="button"
                        className={`${styles.userCardIconBtn} ${styles.userCardIconBtnDanger}`}
                        disabled={!row.deletable}
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
          editing
            ? t("adminUsers.roleEditTitle", { name: userRoleLabel(editing, t) })
            : t("adminUsers.roleCreateTitle")
        }
        placement="right"
        open={editor !== null}
        onClose={closeEditor}
        width={Math.min(
          520,
          typeof window !== "undefined" ? window.innerWidth - 24 : 520,
        )}
        destroyOnHidden
        className={styles.createUserDrawer}
        styles={{ body: { paddingTop: 12, paddingBottom: 24 } }}
        footer={
          <div className={styles.createUserFooter}>
            <Button onClick={closeEditor}>{t("common.cancel")}</Button>
            <Button
              type="primary"
              loading={submitting}
              onClick={() => form.submit()}
            >
              {editing ? t("common.save") : t("common.create")}
            </Button>
          </div>
        }
      >
        <Form<RoleFormValues>
          form={form}
          initialValues={{
            ...formInitialValues,
            permissions: formInitialValues.permissions
              ? [...formInitialValues.permissions]
              : undefined,
          }}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => void onSubmit(values)}
          className={styles.createUserForm}
        >
          <ProfileAvatarPicker
            kind="role"
            avatarUrl={editing?.avatar_url}
            icon={editing ? editing.avatar_icon : pendingIcon}
            onSelectIcon={async (icon) => {
              if (!editing) {
                setPendingIcon(icon);
                setPendingAvatar(null);
                return;
              }
              try {
                const updated = await userRolesApi.update(
                  editing.user_role_id,
                  {
                    avatar_icon: icon,
                  },
                );
                setEditor({
                  ...editing,
                  avatar_url: updated.avatar_url,
                  avatar_icon: updated.avatar_icon,
                });
                void refresh();
              } catch (err) {
                message.error(
                  apiErrorMessage(err, t("experts.avatarUploadFailed"), t),
                );
                throw err;
              }
            }}
            onPick={async (file) => {
              if (!editing) {
                setPendingAvatar(file);
                return;
              }
              try {
                const result = await userRolesApi.uploadAvatar(
                  editing.user_role_id,
                  file,
                );
                setEditor({ ...editing, avatar_url: result.avatar_url });
                void refresh();
              } catch (err) {
                message.error(
                  apiErrorMessage(err, t("experts.avatarUploadFailed"), t),
                );
                throw err;
              }
            }}
            onRemove={
              editing
                ? async () => {
                    try {
                      await userRolesApi.deleteAvatar(editing.user_role_id);
                      setEditor({ ...editing, avatar_url: null });
                      void refresh();
                    } catch (err) {
                      message.error(
                        apiErrorMessage(
                          err,
                          t("experts.avatarRemoveFailed"),
                          t,
                        ),
                      );
                      throw err;
                    }
                  }
                : () => setPendingAvatar(null)
            }
          />
          {editing ? (
            <Form.Item label={t("adminUsers.roleColId")}>
              <Typography.Text
                code
                copyable={{ text: editing.user_role_id }}
                className={styles.roleIdField}
              >
                {editing.user_role_id}
              </Typography.Text>
            </Form.Item>
          ) : (
            <Form.Item
              label={t("adminUsers.roleColId")}
              name="user_role_id"
              extra={t("adminUsers.roleIdHint")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("adminUsers.roleIdRequired"),
                },
                {
                  validator: (_, value: string | undefined) => {
                    const roleId = value?.trim() ?? "";
                    if (!roleId || isValidRoleId(roleId)) {
                      return Promise.resolve();
                    }
                    return Promise.reject(
                      new Error(t("adminUsers.roleIdInvalid")),
                    );
                  },
                },
              ]}
            >
              <Input
                maxLength={ROLE_ID_MAX}
                placeholder={t("adminUsers.roleIdPlaceholder")}
              />
            </Form.Item>
          )}
          <Form.Item
            label={t("adminUsers.roleColName")}
            name="name"
            rules={[
              { required: true, message: t("adminUsers.roleNameRequired") },
            ]}
          >
            <Input maxLength={64} autoFocus prefix={<IdCard size={16} />} />
          </Form.Item>
          <Form.Item
            label={t("adminUsers.roleDescription")}
            name="description"
            className={styles.textAssistField}
          >
            <Input.TextArea
              rows={3}
              placeholder={t("adminUsers.roleDescriptionPlaceholder")}
            />
          </Form.Item>
          <TextAssistBar
            kind="user_role.description"
            getName={() => String(form.getFieldValue("name") ?? "")}
            getText={() => String(form.getFieldValue("description") ?? "")}
            onApply={(text) =>
              form.setFieldsValue({ description: text.slice(0, 500) })
            }
          />
          {locked ? (
            <div className={styles.permAdminHint}>
              <span>{t("adminUsers.roleAdminLocked")}</span>
            </div>
          ) : (
            <>
              <div
                className={`${styles.permAdminHint} ${styles.permSectionHint}`}
              >
                <span>{t("adminUsers.roleCustomHint")}</span>
              </div>
              <Form.Item
                label={t("adminUsers.colPermissions")}
                name="permissions"
                className={styles.createUserPermItem}
              >
                <PermissionCheckboxPicker catalog={permCatalog} />
              </Form.Item>
              <ResourcePolicyFields
                fsTreeRoots={fsTreeRoots}
                workspaceRootAllowed={workspaceRootAllowed}
              />
            </>
          )}
        </Form>
      </Drawer>
    </>
  );
}
