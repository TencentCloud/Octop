import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useTranslation } from "react-i18next";

import AccessGroups from "./AccessGroups";
import {
  memorySharingApi,
  type SharingSession,
  type SharingToken,
  type SharingTokenCreated,
} from "../../../api/modules/memorySharing";

interface Props {
  agentId: string | null;
}

/**「共享记忆」：连接 octop-memory 空间、签发/轮换/撤销客户端 token、绑定专家。 */
export default function MemorySharing({ agentId }: Props) {
  const { t } = useTranslation();
  const [session, setSession] = useState<SharingSession>({ connected: false });
  const [tokens, setTokens] = useState<SharingToken[]>([]);
  const [binding, setBinding] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<SharingTokenCreated | null>(null);
  const [form] = Form.useForm<{ client_name: string }>();

  const refresh = useCallback(async () => {
    const status = await memorySharingApi.status();
    setSession(status);
    if (status.connected) {
      const [list, bind] = await Promise.all([
        memorySharingApi.tokens(),
        agentId
          ? memorySharingApi.binding(agentId)
          : Promise.resolve({ space_id: null }),
      ]);
      setTokens(list.tokens);
      setBinding(bind.space_id);
    } else {
      setTokens([]);
      setBinding(null);
    }
  }, [agentId]);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

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

  const connect = () =>
    run(async () => {
      const next = await memorySharingApi.connect(code.trim());
      setSession(next);
      setCode("");
      message.success(
        t("memory.sharing.connected", "已连接空间 {{space}}", {
          space: next.space_id,
        }),
      );
      await refresh();
    });

  const createToken = () =>
    run(async () => {
      const values = await form.validateFields();
      const token = await memorySharingApi.createToken(
        values.client_name.trim(),
        ["read", "write"],
      );
      setCreated(token);
      form.resetFields();
      await refresh();
    });

  if (!session.connected) {
    return (
      <Card title={t("memory.sharing.title", "共享记忆")}>
        <Typography.Paragraph type="secondary">
          {t(
            "memory.sharing.connectHint",
            "在运行 octop-memory 的机器上执行 octop-memory auth code --space <空间>，把一次性授权码粘贴到这里。",
          )}
        </Typography.Paragraph>
        <Space.Compact style={{ width: "100%", maxWidth: 640 }}>
          <Input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="mcode_…"
          />
          <Button
            type="primary"
            loading={busy}
            disabled={!code.trim()}
            onClick={() => void connect()}
          >
            {t("memory.sharing.connect", "连接空间")}
          </Button>
        </Space.Compact>
      </Card>
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert
        type="success"
        showIcon
        message={t("memory.sharing.connectedTo", "当前空间：{{space}}", {
          space: session.space_id,
        })}
        action={
          <Button
            size="small"
            onClick={() =>
              void run(async () => {
                await memorySharingApi.disconnect();
                setSession({ connected: false });
              })
            }
          >
            {t("memory.sharing.disconnect", "断开")}
          </Button>
        }
      />
      {agentId ? (
        <Alert
          type={binding ? "info" : "warning"}
          showIcon
          message={
            binding
              ? t("memory.sharing.bound", "当前专家已绑定空间 {{space}}", {
                  space: binding,
                })
              : t("memory.sharing.unbound", "当前专家尚未绑定空间")
          }
          action={
            <Button
              size="small"
              loading={busy}
              onClick={() =>
                void run(async () => {
                  await memorySharingApi.bind(agentId, session.space_id || "");
                  setBinding(session.space_id || null);
                })
              }
            >
              {t("memory.sharing.bind", "绑定当前专家")}
            </Button>
          }
        />
      ) : null}
      <AccessGroups connected={session.connected} />
      <Card
        title={t("memory.sharing.tokens", "客户端 Token")}
        extra={
          <Form form={form} layout="inline" onFinish={() => void createToken()}>
            <Form.Item
              name="client_name"
              rules={[
                {
                  required: true,
                  message: t("memory.sharing.clientRequired", "填写客户端名称"),
                },
              ]}
            >
              <Input placeholder="codex-laptop" style={{ width: 180 }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={busy}>
              {t("memory.sharing.create", "生成 Token")}
            </Button>
          </Form>
        }
      >
        <Table<SharingToken>
          rowKey="token_id"
          size="small"
          dataSource={tokens}
          pagination={false}
          columns={[
            {
              title: t("memory.sharing.client", "客户端"),
              dataIndex: "client_name",
            },
            {
              title: t("memory.sharing.scopes", "权限"),
              dataIndex: "scopes",
              render: (scopes: string[]) => scopes.join(", "),
            },
            {
              title: t("memory.sharing.hint", "提示"),
              dataIndex: "token_hint",
            },
            {
              title: t("memory.sharing.lastUsed", "最近使用"),
              dataIndex: "last_used_at",
              render: (value: string | null) => value || "-",
            },
            {
              title: t("memory.sharing.status", "状态"),
              dataIndex: "revoked_at",
              render: (value: string | null) =>
                value ? (
                  <Tag>{t("memory.sharing.revoked", "已撤销")}</Tag>
                ) : (
                  <Tag color="green">{t("memory.sharing.active", "有效")}</Tag>
                ),
            },
            {
              title: t("memory.sharing.actions", "操作"),
              render: (_: unknown, token) => (
                <Space size={4}>
                  <Button
                    type="link"
                    size="small"
                    disabled={!!token.revoked_at}
                    onClick={() =>
                      void run(async () => {
                        const rotated = await memorySharingApi.rotateToken(
                          token.token_id,
                        );
                        setCreated(rotated);
                        await refresh();
                      })
                    }
                  >
                    {t("memory.sharing.rotate", "轮换")}
                  </Button>
                  <Popconfirm
                    title={t(
                      "memory.sharing.revokeConfirm",
                      "撤销这个 Token？",
                    )}
                    onConfirm={() =>
                      void run(async () => {
                        await memorySharingApi.revokeToken(token.token_id);
                        await refresh();
                      })
                    }
                  >
                    <Button
                      type="link"
                      size="small"
                      danger
                      disabled={!!token.revoked_at}
                    >
                      {t("memory.sharing.revoke", "撤销")}
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      {created ? (
        <Alert
          type="warning"
          showIcon
          message={t(
            "memory.sharing.createdTitle",
            "Token 只显示这一次，请立即复制",
          )}
          description={
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text code copyable>
                {created.token}
              </Typography.Text>
              <Typography.Paragraph
                type="secondary"
                style={{ marginBottom: 0 }}
              >
                {t(
                  "memory.sharing.clientHint",
                  "客户端 MCP 配置：url 填 http://<memory-host>:8790/mcp/，headers 里带 Authorization: Bearer <token>。",
                )}
              </Typography.Paragraph>
            </Space>
          }
          closable
          onClose={() => setCreated(null)}
        />
      ) : null}
    </Space>
  );
}
