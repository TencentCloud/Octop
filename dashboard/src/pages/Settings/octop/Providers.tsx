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

import { useEffect, useState } from "react";
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
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<FormValues>();

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await request<ProviderRow[]>("/providers");
      setRows(data);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const onCreate = async (values: FormValues) => {
    setSubmitting(true);
    try {
      // Default ``note`` to "private to <user>" when blank so list rows
      // visibly distinguish per-user from shared providers.
      const body: FormValues = { ...values };
      if (!body.note) {
        const me = await authApi.me().catch(() => null);
        body.note = me ? `private to ${me.username}` : "private";
      }
      await request("/providers", {
        method: "POST",
        body: JSON.stringify(body),
      });
      message.success(`Provider "${values.name}" created`);
      form.resetFields();
      setCreateOpen(false);
      void refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (row: ProviderRow) => {
    try {
      await request(`/admin/providers/${row.id}`, { method: "DELETE" });
      message.success("Deleted");
      void refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <Card
      title="Providers"
      extra={
        <Space>
          <Button icon={<RefreshCw size={14} />} onClick={() => void refresh()}>
            Refresh
          </Button>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            onClick={() => setCreateOpen(true)}
          >
            New provider
          </Button>
        </Space>
      }
    >
      <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
        All providers are admin-managed and globally available to every agent.
      </Text>

      <Table<ProviderRow>
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: "Name", dataIndex: "name" },
          {
            title: "Kind",
            dataIndex: "kind",
            render: (k) => <Tag>{k}</Tag>,
          },
          { title: "Note", dataIndex: "note" },
          {
            title: "",
            width: 80,
            render: (_, row) => (
              <Popconfirm
                title={`Delete ${row.name}?`}
                onConfirm={() => onDelete(row)}
              >
                <Button danger size="small" type="link">
                  Delete
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />

      <Modal
        title="New provider"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="Create"
        confirmLoading={submitting}
      >
        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={onCreate}
          initialValues={{ kind: "openai" }}
        >
          <Form.Item
            label="Name"
            name="name"
            rules={[{ required: true, message: "Name is required" }]}
          >
            <Input placeholder="my-openai" />
          </Form.Item>
          <Form.Item label="Kind" name="kind" rules={[{ required: true }]}>
            <Select options={PROVIDER_KINDS} />
          </Form.Item>
          <Form.Item label="Base URL (optional)" name="base_url">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item label="API key (optional)" name="api_key">
            <Input.Password placeholder="sk-…" />
          </Form.Item>
          <Form.Item label="Default model (optional)" name="model">
            <Input placeholder="gpt-4o-mini" />
          </Form.Item>
          <Form.Item label="Note" name="note">
            <Input placeholder="private to <you>" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
