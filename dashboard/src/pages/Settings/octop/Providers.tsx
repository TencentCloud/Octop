/**
 * Octop settings — Providers editor.
 *
 * Plan §14.6: list providers visible to the current user, show a "shared"
 * badge for admin-scope rows (``user_id === null``) with their ``note``
 * field, allow non-admins to create their own. The full edit drawer
 * (kind-specific config schema, secret reveal, etc.) is deferred to phase
 * 15 — this page covers list + create + delete which is enough to drive
 * the agent settings editor (which depends on a non-empty provider list).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  Popconfirm,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import { Plus, RefreshCw } from "lucide-react";
import { request } from "../../../api/request";
import { authApi } from "../../../api/modules/auth";

const { Text } = Typography;

interface ProviderRow {
  id: number;
  name: string;
  kind: string;
  base_url: string | null;
  api_key: string | null;
  note: string | null;
  enabled: boolean;
}

interface FormValues {
  name: string;
  kind: string;
  base_url?: string;
  api_key?: string;
  model?: string;
  note?: string;
}

const PROVIDER_KINDS = [
  { value: "openai", label: "OpenAI / OpenAI-compatible" },
  { value: "anthropic", label: "Anthropic" },
  { value: "ollama", label: "Ollama" },
];

export default function OctopProvidersPage() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<FormValues>();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<ProviderRow[]>("/providers");
      setRows(data);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminProviders.loadFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onCreate = async (values: FormValues) => {
    setSubmitting(true);
    try {
      // Default ``note`` to "private to <user>" when blank so list rows
      // visibly distinguish per-user from shared providers.
      const body: FormValues = { ...values };
      if (!body.note) {
        const me = await authApi.me().catch(() => null);
        body.note = me
          ? t("adminProviders.notePrivateTo", { username: me.username })
          : t("adminProviders.notePrivate");
      }
      await request("/providers", {
        method: "POST",
        body: JSON.stringify(body),
      });
      message.success(t("adminProviders.created", { name: values.name }));
      form.resetFields();
      setCreateOpen(false);
      void refresh();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("adminProviders.createFailed"),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (row: ProviderRow) => {
    try {
      await request(`/admin/providers/${row.id}`, { method: "DELETE" });
      message.success(t("adminProviders.deleted"));
      void refresh();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.deleteFailed"),
      );
    }
  };

  return (
    <Card
      title={t("adminProviders.title")}
      extra={
        <Space>
          <Button icon={<RefreshCw size={14} />} onClick={() => void refresh()}>
            {t("common.refresh")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            onClick={() => setCreateOpen(true)}
          >
            {t("adminProviders.newProvider")}
          </Button>
        </Space>
      }
    >
      <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
        {t("adminProviders.pageDescription")}
      </Text>

      <Table<ProviderRow>
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: t("adminProviders.colName"), dataIndex: "name" },
          {
            title: t("adminProviders.colKind"),
            dataIndex: "kind",
            render: (k) => <Tag>{k}</Tag>,
          },
          { title: t("adminProviders.colNote"), dataIndex: "note" },
          {
            title: "",
            width: 80,
            render: (_, row) => (
              <Popconfirm
                title={t("adminProviders.deleteConfirm", { name: row.name })}
                onConfirm={() => onDelete(row)}
              >
                <Button danger size="small" type="link">
                  {t("common.delete")}
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />

      <Modal
        title={t("adminProviders.newProvider")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText={t("common.create")}
        confirmLoading={submitting}
      >
        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={onCreate}
          initialValues={{ kind: "openai" }}
        >
          <Form.Item
            label={t("adminProviders.colName")}
            name="name"
            rules={[
              { required: true, message: t("adminProviders.nameRequired") },
            ]}
          >
            <Input placeholder="my-openai" />
          </Form.Item>
          <Form.Item
            label={t("adminProviders.colKind")}
            name="kind"
            rules={[{ required: true }]}
          >
            <Select options={PROVIDER_KINDS} />
          </Form.Item>
          <Form.Item label={t("adminProviders.fieldBaseUrl")} name="base_url">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item label={t("adminProviders.fieldApiKey")} name="api_key">
            <Input.Password placeholder="sk-…" />
          </Form.Item>
          <Form.Item label={t("adminProviders.fieldModel")} name="model">
            <Input placeholder="gpt-4o-mini" />
          </Form.Item>
          <Form.Item label={t("adminProviders.colNote")} name="note">
            <Input placeholder={t("adminProviders.notePlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
