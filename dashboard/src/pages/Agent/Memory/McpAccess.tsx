/**
 * MCP 接入 — user-level tokens for the memory MCP server.
 *
 * Embedded as a tab inside MemoryPanel (only when the host page opts in via
 * ``showMcpTab``), so the sidebar keeps its existing keys. External agents
 * (Claude Code / Codex / Cursor / Kiro / DSH) authenticate against
 * ``/mcp/memory`` with the plaintext token; the server only ever shows it once.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { TableColumnsType } from "antd";
import { KeyRound, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  memoryMcpApi,
  type CreateMemoryMcpTokenBody,
  type MemoryMcpToken,
  type MemoryMcpTokenCreated,
} from "../../../api/modules/memoryMcp";
import { useAgent } from "../../../context/AgentContext";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { message } from "@/utils/antdMessage";
import { copyText } from "../../../utils/copyText";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import styles from "./MemorySettings.module.less";

interface CreateFormValues {
  name: string;
  expert_ids?: string[];
}

export default function McpAccess() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const { agents } = useAgent();

  const [tokens, setTokens] = useState<MemoryMcpToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ detail?: string } | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<MemoryMcpTokenCreated | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [form] = Form.useForm<CreateFormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setTokens(await memoryMcpApi.list());
    } catch (e) {
      setLoadError({ detail: e instanceof Error ? e.message : undefined });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Token expert_ids are agent ids, so the picker reuses the loaded agent list
  // instead of introducing another endpoint. Bridge shadows are excluded: they
  // are remote placeholders that cannot own a local memory store.
  const expertOptions = useMemo(
    () =>
      agents
        .filter((agent) => !agent.bridge)
        .map((agent) => ({
          value: agent.agent_id,
          label: `${agent.name} · ${agent.agent_id}`,
        })),
    [agents],
  );

  const expertNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) map.set(agent.agent_id, agent.name);
    return map;
  }, [agents]);

  const handleCreate = async () => {
    let values: CreateFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setCreating(true);
    try {
      const body: CreateMemoryMcpTokenBody = {
        name: values.name.trim(),
        expert_ids: values.expert_ids?.length ? values.expert_ids : null,
      };
      const result = await memoryMcpApi.create(body);
      setCreateOpen(false);
      form.resetFields();
      setCreated(result);
      await load();
    } catch (e) {
      message.error(
        e instanceof Error
          ? e.message
          : t("memory.mcp.createFailed", "创建失败，请重试"),
      );
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = async () => {
    if (!created) return;
    const ok = await copyText(created.plaintext);
    if (ok) {
      message.success(t("memory.mcp.copied", "已复制"));
    } else {
      message.error(t("memory.mcp.copyFailed", "复制失败，请手动选中后复制"));
    }
  };

  const handleRevoke = async (token: MemoryMcpToken) => {
    setRevokingId(token.token_id);
    try {
      await memoryMcpApi.revoke(token.token_id);
      message.success(t("memory.mcp.revoked", "Token 已撤销"));
      await load();
    } catch (e) {
      message.error(
        e instanceof Error
          ? e.message
          : t("memory.mcp.revokeFailed", "撤销失败，请重试"),
      );
    } finally {
      setRevokingId(null);
    }
  };

  const columns: TableColumnsType<MemoryMcpToken> = [
    {
      title: t("memory.mcp.columnName", "名称"),
      dataIndex: "name",
      key: "name",
      render: (name: string) => (
        <Typography.Text strong>{name}</Typography.Text>
      ),
    },
    {
      title: t("memory.mcp.columnHint", "Token 提示"),
      dataIndex: "token_hint",
      key: "token_hint",
      render: (hint: string) => <Typography.Text code>{hint}</Typography.Text>,
    },
    {
      title: t("memory.mcp.columnExperts", "专家范围"),
      dataIndex: "expert_ids",
      key: "expert_ids",
      render: (_: unknown, token) => {
        const ids = token.expert_ids ?? [];
        if (ids.length === 0) {
          return <Tag>{t("memory.mcp.allExperts", "不限专家")}</Tag>;
        }
        return (
          <Space size={[4, 4]} wrap>
            <Typography.Text type="secondary">
              {t("memory.mcp.expertCount", "{{count}} 个专家", {
                count: ids.length,
              })}
            </Typography.Text>
            {ids.map((id) => (
              <Tag key={id} title={id}>
                {expertNames.get(id) ?? id}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: t("memory.mcp.columnCreatedAt", "创建时间"),
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => (
        <span>{formatServerIsoDateTime(value, timeZone)}</span>
      ),
    },
    {
      title: t("memory.mcp.columnLastUsedAt", "最近使用"),
      dataIndex: "last_used_at",
      key: "last_used_at",
      render: (value: string | null) =>
        value ? (
          <span>{formatServerIsoDateTime(value, timeZone)}</span>
        ) : (
          <Typography.Text type="secondary">
            {t("memory.mcp.neverUsed", "从未使用")}
          </Typography.Text>
        ),
    },
    {
      title: t("memory.mcp.columnStatus", "状态"),
      dataIndex: "revoked_at",
      key: "status",
      render: (revokedAt: string | null) =>
        revokedAt ? (
          <Tag>{t("memory.mcp.statusRevoked", "已撤销")}</Tag>
        ) : (
          <Tag color="success">{t("memory.mcp.statusActive", "有效")}</Tag>
        ),
    },
    {
      title: t("memory.mcp.columnActions", "操作"),
      key: "actions",
      width: 110,
      render: (_: unknown, token) => (
        <Popconfirm
          title={t("memory.mcp.revokeConfirmTitle", "撤销这个 Token？")}
          description={t(
            "memory.mcp.revokeConfirmDesc",
            "撤销后，使用该 Token 的外部 Agent 将立即无法访问记忆，且不可恢复。",
          )}
          okText={t("memory.mcp.revoke", "撤销")}
          cancelText={t("common.cancel", "取消")}
          okButtonProps={{ danger: true }}
          disabled={!!token.revoked_at}
          onConfirm={() => void handleRevoke(token)}
        >
          <Button
            danger
            size="small"
            loading={revokingId === token.token_id}
            disabled={!!token.revoked_at}
          >
            {t("memory.mcp.revoke", "撤销")}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className={styles.settingsPage}>
      <div className={styles.pageHeader}>
        <span className={styles.headerIcon}>
          <KeyRound size={22} />
        </span>
        <div>
          <h2>{t("memory.mcp.title", "MCP 接入")}</h2>
          <p>
            {t(
              "memory.mcp.description",
              "外部 Agent（Claude Code / Codex / Cursor / Kiro / DSH）使用这里的 Token 访问 {{endpoint}}。Token 只显示一次，丢失后请重建。",
              { endpoint: "/mcp/memory" },
            )}
          </p>
        </div>
        <Button
          type="primary"
          icon={<Plus size={15} />}
          style={{ marginLeft: "auto", flexShrink: 0 }}
          onClick={() => setCreateOpen(true)}
        >
          {t("memory.mcp.create", "创建 Token")}
        </Button>
      </div>

      {loadError ? (
        <Alert
          type="error"
          showIcon
          message={
            loadError.detail ?? t("memory.mcp.loadFailed", "Token 列表加载失败")
          }
          action={
            <Button size="small" onClick={() => void load()}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      ) : null}

      {loading && tokens.length === 0 ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : (
        <Table<MemoryMcpToken>
          rowKey="token_id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={tokens}
          pagination={false}
          scroll={{ x: 880 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Space direction="vertical" size={2}>
                    <Typography.Text>
                      {t("memory.mcp.empty", "还没有 MCP Token")}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {t(
                        "memory.mcp.emptyHint",
                        "创建后即可在外部 Agent 中接入你的记忆。",
                      )}
                    </Typography.Text>
                  </Space>
                }
              >
                <Button type="primary" onClick={() => setCreateOpen(true)}>
                  {t("memory.mcp.create", "创建 Token")}
                </Button>
              </Empty>
            ),
          }}
        />
      )}

      <Modal
        open={createOpen}
        title={t("memory.mcp.createTitle", "创建 MCP Token")}
        okText={t("memory.mcp.submit", "创建")}
        cancelText={t("common.cancel", "取消")}
        confirmLoading={creating}
        onOk={() => void handleCreate()}
        onCancel={() => {
          if (creating) return;
          setCreateOpen(false);
          form.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item
            name="name"
            label={t("memory.mcp.nameLabel", "名称")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("memory.mcp.nameRequired", "请填写名称"),
              },
              {
                max: 64,
                message: t("memory.mcp.nameTooLong", "名称最多 64 个字符"),
              },
            ]}
          >
            <Input
              maxLength={64}
              autoComplete="off"
              placeholder={t(
                "memory.mcp.namePlaceholder",
                "例如 codex@macbook",
              )}
            />
          </Form.Item>
          <Form.Item
            name="expert_ids"
            label={t("memory.mcp.expertsLabel", "专家范围")}
            extra={t(
              "memory.mcp.expertsHint",
              "不选择时，该 Token 可访问你有权限访问的所有专家。",
            )}
          >
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={expertOptions}
              placeholder={t(
                "memory.mcp.expertsPlaceholder",
                "不选择表示不限专家",
              )}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={created !== null}
        title={t("memory.mcp.plaintextTitle", "Token 已创建")}
        maskClosable={false}
        onCancel={() => setCreated(null)}
        footer={
          <Space>
            <Button onClick={() => void handleCopy()}>
              {t("memory.mcp.copy", "复制")}
            </Button>
            <Button type="primary" onClick={() => setCreated(null)}>
              {t("memory.mcp.close", "我已保存，关闭")}
            </Button>
          </Space>
        }
      >
        {created ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Alert
              type="warning"
              showIcon
              message={t(
                "memory.mcp.plaintextWarning",
                "请立即复制并妥善保存。此 Token 只显示这一次，关闭后无法再次查看。",
              )}
            />
            <Typography.Text strong>{created.token.name}</Typography.Text>
            <Input readOnly value={created.plaintext} />
          </Space>
        ) : null}
      </Modal>
    </div>
  );
}
