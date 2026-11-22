import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useTranslation } from "react-i18next";

import {
  memorySharingGroupsApi,
  type AccessGroup,
  type GroupToken,
} from "../../../api/modules/memorySharing";

const TERMINALS = [
  { key: "codex", label: "Codex" },
  { key: "cursor", label: "Cursor" },
  { key: "claude-code", label: "Claude Code" },
  { key: "kiro", label: "Kiro" },
  { key: "dsh", label: "DSH" },
];

function configSnippet(token: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        "octop-memory": {
          type: "streamable-http",
          url: "http://<memory-host>:8790/mcp/",
          headers: { Authorization: `Bearer ${token}` },
        },
      },
    },
    null,
    2,
  );
}

export default function AccessGroups({ connected }: { connected: boolean }) {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<AccessGroup[]>([]);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm<{ name: string; clients: string[] }>();

  const load = useCallback(async () => {
    if (!connected) {
      setGroups([]);
      return;
    }
    const data = await memorySharingGroupsApi.list();
    setGroups(data.groups);
  }, [connected]);

  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);

  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    try {
      await task();
    } catch (error) {
      message.error(
        (error as Error).message || t("memory.sharing.failed", "操作失败"),
      );
    } finally {
      setBusy(false);
    }
  };

  const create = () =>
    run(async () => {
      const values = await form.validateFields();
      const created = await memorySharingGroupsApi.create(
        values.name.trim(),
        values.clients,
        ["read", "write"],
      );
      setSecrets((prev) => {
        const next = { ...prev };
        for (const token of created.tokens)
          next[`${created.group_id}:${token.client_name}`] = token.token;
        return next;
      });
      form.resetFields();
      await load();
    });

  const setTerminal = (group: AccessGroup, client: string, enabled: boolean) =>
    run(async () => {
      if (enabled) {
        const created = await memorySharingGroupsApi.enable(
          group.group_id,
          client,
        );
        setSecrets((prev) => ({
          ...prev,
          [`${group.group_id}:${client}`]: created.token,
        }));
      } else {
        await memorySharingGroupsApi.disable(group.group_id, client);
      }
      await load();
    });

  const rotate = (group: AccessGroup, client: string) =>
    run(async () => {
      const created = await memorySharingGroupsApi.rotate(
        group.group_id,
        client,
      );
      setSecrets((prev) => ({
        ...prev,
        [`${group.group_id}:${client}`]: created.token,
      }));
      await load();
    });

  const showConfig = (group: AccessGroup, token: GroupToken) => {
    const secret = secrets[`${group.group_id}:${token.client_name}`];
    Modal.info({
      title: `${group.name} / ${token.client_name}`,
      width: 720,
      content: secret ? (
        <Space direction="vertical" style={{ width: "100%" }} size={8}>
          <Alert
            type="warning"
            showIcon
            message={t(
              "memory.sharing.createdTitle",
              "Token 只显示这一次，请立即复制",
            )}
          />
          <Typography.Text code copyable>
            {secret}
          </Typography.Text>
          <Typography.Paragraph
            style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}
            code
          >
            {configSnippet(secret)}
          </Typography.Paragraph>
        </Space>
      ) : (
        <Typography.Paragraph type="secondary">
          {t(
            "memory.sharing.configUnavailable",
            "明文只在生成/轮换时显示。需要新配置请点“轮换”，旧 key 会立即失效。",
          )}
        </Typography.Paragraph>
      ),
    });
  };

  return (
    <Card
      title={t("memory.sharing.terminalsTitle", "AI 终端接入")}
      extra={
        <Typography.Text type="secondary">
          {t(
            "memory.sharing.terminalsHint",
            "一次接入所有终端；每个终端独立 token，可单独禁用",
          )}
        </Typography.Text>
      }
    >
      <Form
        form={form}
        layout="inline"
        initialValues={{ clients: ["codex", "cursor"] }}
      >
        <Form.Item name="name" rules={[{ required: true }]}>
          <Input
            placeholder={t("memory.sharing.groupName", "接入组名称")}
            style={{ width: 160 }}
          />
        </Form.Item>
        <Form.Item name="clients">
          <Checkbox.Group
            options={TERMINALS.map((item) => ({
              label: item.label,
              value: item.key,
            }))}
          />
        </Form.Item>
        <Button type="primary" loading={busy} onClick={() => void create()}>
          {t("memory.sharing.connectAll", "一键接入所有终端")}
        </Button>
      </Form>
      <Space
        direction="vertical"
        size={12}
        style={{ width: "100%", marginTop: 16 }}
      >
        {groups.map((group) => (
          <Card key={group.group_id} size="small" title={group.name}>
            <Table<GroupToken>
              rowKey="token_id"
              size="small"
              pagination={false}
              dataSource={group.tokens}
              columns={[
                {
                  title: t("memory.sharing.client", "终端"),
                  dataIndex: "client_name",
                  render: (client: string) => client,
                },
                {
                  title: t("memory.sharing.status", "状态"),
                  render: (_: unknown, token) =>
                    token.revoked_at ? (
                      <Tag>{t("memory.sharing.revoked", "已禁用")}</Tag>
                    ) : (
                      <Tag color="green">
                        {t("memory.sharing.active", "启用")}
                      </Tag>
                    ),
                },
                {
                  title: t("memory.sharing.actions", "操作"),
                  render: (_: unknown, token) => (
                    <Space>
                      <Switch
                        size="small"
                        checked={!token.revoked_at}
                        loading={busy}
                        onChange={(checked) =>
                          void setTerminal(group, token.client_name, checked)
                        }
                      />
                      <Button
                        type="link"
                        size="small"
                        onClick={() => showConfig(group, token)}
                      >
                        {t("memory.sharing.config", "配置")}
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        onClick={() => void rotate(group, token.client_name)}
                      >
                        {t("memory.sharing.rotate", "轮换")}
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        ))}
        {connected && groups.length === 0 ? (
          <Typography.Text type="secondary">
            {t(
              "memory.sharing.noGroups",
              "还没有接入组，选择终端后点“一键接入所有终端”。",
            )}
          </Typography.Text>
        ) : null}
      </Space>
    </Card>
  );
}
