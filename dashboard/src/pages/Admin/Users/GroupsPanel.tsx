import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Spin,
} from "antd";
import { Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ResizableTable } from "@/components/ResizableTable";
import { message } from "@/utils/antdMessage";
import { request } from "../../../api/request";
import { userGroupsApi, type UserGroup } from "../../../api/modules/userGroups";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";

interface UserOption {
  id: number;
  username: string;
  display_name: string | null;
}

interface GroupFormValues {
  name: string;
  description?: string;
  user_ids?: number[];
}

export default function GroupsPanel() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<UserGroup[]>([]);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<UserGroup | null>(null);
  const [form] = Form.useForm<GroupFormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [groups, accounts] = await Promise.all([
        userGroupsApi.list(),
        request<UserOption[]>("/users"),
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

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({ name: "", description: "", user_ids: [] });
    setOpen(true);
  };

  const openEdit = async (row: UserGroup) => {
    setEditing(row);
    form.setFieldsValue({
      name: row.name,
      description: row.description ?? "",
      user_ids: [],
    });
    setOpen(true);
    try {
      const members = await userGroupsApi.members(row.user_group_id);
      form.setFieldValue("user_ids", members.user_ids);
    } catch (error) {
      message.error(apiErrorMessage(error, t("adminUsers.groupLoadFailed"), t));
    }
  };

  const save = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const saved = editing
        ? await userGroupsApi.update(editing.user_group_id, {
            name: values.name.trim(),
            description: values.description?.trim() || null,
          })
        : await userGroupsApi.create({
            name: values.name.trim(),
            description: values.description?.trim() || null,
          });
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

  return (
    <div>
      <TabPanelHeader
        icon={<UsersRound size={22} />}
        title={t("adminUsers.tabGroups")}
        description={t("adminUsers.groupHint")}
        actions={
          <Button type="primary" icon={<Plus size={16} />} onClick={openCreate}>
            {t("adminUsers.groupCreate")}
          </Button>
        }
      />
      <Spin spinning={loading}>
        <ResizableTable
          rowKey="user_group_id"
          dataSource={rows}
          pagination={false}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("adminUsers.groupEmpty")}
              />
            ),
          }}
          columns={[
            { title: t("adminUsers.groupName"), dataIndex: "name" },
            {
              title: t("adminUsers.groupDescription"),
              dataIndex: "description",
              render: (value: string | null) => value || "—",
            },
            {
              title: t("adminUsers.groupMembers"),
              dataIndex: "member_count",
              width: 120,
              render: (count: number) =>
                t("adminUsers.groupMemberCount", { count }),
            },
            {
              title: "",
              width: 120,
              render: (_value, row) => (
                <Space>
                  <Button
                    type="text"
                    icon={<Pencil size={16} />}
                    onClick={() => void openEdit(row)}
                  />
                  <Popconfirm
                    title={t("adminUsers.groupDeleteConfirm", {
                      name: row.name,
                    })}
                    onConfirm={() => void remove(row)}
                  >
                    <Button type="text" danger icon={<Trash2 size={16} />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Spin>
      <Drawer
        title={
          editing
            ? t("adminUsers.groupEditTitle", { name: editing.name })
            : t("adminUsers.groupCreate")
        }
        open={open}
        onClose={() => setOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void save()}>
            {t("common.save")}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={t("adminUsers.groupName")}
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item
            name="description"
            label={t("adminUsers.groupDescription")}
          >
            <Input.TextArea rows={3} maxLength={500} />
          </Form.Item>
          <Form.Item name="user_ids" label={t("adminUsers.groupMembers")}>
            <Select
              mode="multiple"
              optionFilterProp="label"
              options={users.map((user) => ({
                value: user.id,
                label: user.display_name
                  ? `${user.display_name} (${user.username})`
                  : user.username,
              }))}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
