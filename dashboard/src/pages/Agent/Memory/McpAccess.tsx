/**
 * MCP 接入 — user-level tokens for the memory MCP server.
 *
 * Embedded as a tab inside MemoryPanel (only when the host page opts in via
 * ``showMcpTab``), so the sidebar keeps its existing keys. External agents
 * (Claude Code / Codex / Cursor / Kiro / DSH) authenticate against
 * ``/mcp/memory`` with the plaintext token; the server only ever shows it once.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
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
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { TableColumnsType } from "antd";
import { KeyRound, Plus, Terminal, Trash2, UserRoundCog } from "lucide-react";
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

/**
 * Sentinel for "no expert binding" in the single-select expert pickers.
 * Choosing it sends ``expert_ids: null``, which brings the
 * ``X-Octop-Agent-Id`` requirement back on MCP requests.
 */
const UNRESTRICTED_EXPERT = "__unrestricted__";

/** Public setup guide for the clients this tab issues tokens to. */
const MCP_SETUP_DOCS_URL =
  "https://github.com/TencentCloud/octop-memory/blob/main/plugins/harness/AI-SETUP.md";

interface CreateFormValues {
  name: string;
  expert_id: string;
}

interface SwitchExpertFormValues {
  expert_id?: string;
}

/** One row of the expanded client panel: name, last use, calls, toggle. */
/** 操作列的文字按钮：去掉默认左右内边距，三个按钮挤在一行里也不松散。 */
const ACTION_TEXT_STYLE = { paddingInline: 4, height: 24 } as const;

const CLIENT_ROW_STYLE: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(120px, 1fr) 190px 72px 52px",
  columnGap: 12,
  alignItems: "center",
};

export default function McpAccess() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const { agents, activeAgentId } = useAgent();

  const [tokens, setTokens] = useState<MemoryMcpToken[]>([]);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ detail?: string } | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createExpertDefault, setCreateExpertDefault] = useState<string>("");
  const [created, setCreated] = useState<MemoryMcpTokenCreated | null>(null);
  /**
   * Plaintexts seen this session, keyed by token id. The server keeps only the
   * digest, so a row without an entry can only copy after a rotate.
   */
  const [plaintextByToken, setPlaintextByToken] = useState<
    Record<string, string>
  >({});
  /** Token whose "setup command" modal is open, if any. */
  const [commandTarget, setCommandTarget] = useState<MemoryMcpToken | null>(
    null,
  );
  const [rotating, setRotating] = useState(false);
  /** Command to show once the token was regenerated; null before that. */
  const [rotatedCommand, setRotatedCommand] = useState<string | null>(null);
  const [rotatedPlaintext, setRotatedPlaintext] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  /** ``token_id:client`` currently being enabled/disabled. */
  const [togglingClient, setTogglingClient] = useState<string | null>(null);
  const [switchTarget, setSwitchTarget] = useState<MemoryMcpToken | null>(null);
  const [switching, setSwitching] = useState(false);
  const [form] = Form.useForm<CreateFormValues>();
  const [switchForm] = Form.useForm<SwitchExpertFormValues>();

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

  const expertPickerOptions = useMemo(
    () => [
      ...expertOptions,
      {
        value: UNRESTRICTED_EXPERT,
        label: t(
          "memory.mcp.expertUnrestricted",
          "不限定专家（需客户端带 X-Octop-Agent-Id）",
        ),
      },
    ],
    [expertOptions, t],
  );

  const expertNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) map.set(agent.agent_id, agent.name);
    return map;
  }, [agents]);

  /** Default for a new token: the expert the user is looking at right now. */
  const defaultExpertId = useMemo(() => {
    if (expertOptions.some((option) => option.value === activeAgentId)) {
      return activeAgentId as string;
    }
    return expertOptions[0]?.value ?? UNRESTRICTED_EXPERT;
  }, [expertOptions, activeAgentId]);

  const openCreate = () => {
    setCreateExpertDefault(defaultExpertId);
    setCreateOpen(true);
  };

  // The create modal is destroyed on close, so the default expert can only be
  // written once its Form is mounted (same commit as ``createOpen``).
  useEffect(() => {
    if (!createOpen) return;
    form.setFieldsValue({ expert_id: createExpertDefault });
  }, [createOpen, createExpertDefault, form]);

  const openSwitchExpert = (token: MemoryMcpToken) => {
    setSwitchTarget(token);
  };

  useEffect(() => {
    if (!switchTarget) return;
    const ids = switchTarget.expert_ids ?? [];
    switchForm.setFieldsValue({
      expert_id: ids.length === 1 ? ids[0] : undefined,
    });
  }, [switchTarget, switchForm]);

  const buildClientConfig = (plaintext: string) =>
    JSON.stringify(
      {
        mcpServers: {
          "octop-memory": {
            type: "http",
            url: `${origin}/mcp/memory/`,
            headers: { Authorization: `Bearer ${plaintext}` },
          },
        },
      },
      null,
      2,
    );

  const buildInstallScript = (plaintext: string) =>
    `curl -fsSL https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.sh | sh -s -- --url ${origin}/mcp/memory/ --token ${plaintext}`;

  const buildAiPrompt = (plaintext: string) =>
    [
      "请按 https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/AI-SETUP.md 完成 octop-memory 终端接入。",
      `OCTOP_URL=${origin}/mcp/memory/`,
      `OCTOP_TOKEN=${plaintext}`,
      "安装后按文档里的验证步骤检查召回与上报，并把结果告诉我。",
    ].join("\n");

  const buildInstallPowerShell = (plaintext: string) =>
    `irm https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.ps1 -OutFile install.ps1; .\\install.ps1 -Url ${origin}/mcp/memory/ -Token ${plaintext}`;

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
        // A token bound to exactly one expert needs no agent header on MCP
        // requests; null means "unrestricted", which still requires it.
        expert_ids:
          values.expert_id === UNRESTRICTED_EXPERT ? null : [values.expert_id],
      };
      const result = await memoryMcpApi.create(body);
      setCreateOpen(false);
      form.resetFields();
      setCreated(result);
      // Keep the secret for this session so the row can copy its command again.
      setPlaintextByToken((prev) => ({
        ...prev,
        [result.token.token_id]: result.plaintext,
      }));
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

  const handleSwitchExpert = async () => {
    if (!switchTarget) return;
    let values: SwitchExpertFormValues;
    try {
      values = await switchForm.validateFields();
    } catch {
      return;
    }
    const expertId = values.expert_id;
    setSwitching(true);
    try {
      await memoryMcpApi.update(switchTarget.token_id, {
        expert_ids:
          !expertId || expertId === UNRESTRICTED_EXPERT ? null : [expertId],
      });
      message.success(t("memory.mcp.switchExpertSuccess", "已切换上报专家"));
      setSwitchTarget(null);
      switchForm.resetFields();
      await load();
    } catch (e) {
      message.error(
        e instanceof Error
          ? e.message
          : t("memory.mcp.switchExpertFailed", "切换失败，请重试"),
      );
    } finally {
      setSwitching(false);
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

  const copySetupCommand = async (command: string) => {
    const ok = await copyText(command);
    if (ok) {
      message.success(t("memory.mcp.copied", "已复制"));
    } else {
      message.error(t("memory.mcp.copyFailed", "复制失败，请手动选中后复制"));
    }
  };

  const handleCommandClick = (token: MemoryMcpToken) => {
    const plaintext = plaintextByToken[token.token_id];
    if (plaintext) {
      void copySetupCommand(buildClientConfig(plaintext));
      return;
    }
    setRotatedCommand(null);
    setRotatedPlaintext(null);
    setCommandTarget(token);
  };

  const handleRegenerateCommand = async () => {
    if (!commandTarget) return;
    setRotating(true);
    try {
      const result = await memoryMcpApi.rotate(commandTarget.token_id);
      const command = buildClientConfig(result.plaintext);
      setPlaintextByToken((prev) => ({
        ...prev,
        [result.token.token_id]: result.plaintext,
      }));
      setRotatedCommand(command);
      setRotatedPlaintext(result.plaintext);
      await copySetupCommand(command);
    } catch (e) {
      message.error(
        e instanceof Error
          ? e.message
          : t("memory.mcp.rotateFailed", "重新生成失败，请重试"),
      );
    } finally {
      setRotating(false);
    }
  };

  const closeCommandModal = () => {
    if (rotating) return;
    const rotated = rotatedCommand !== null;
    setCommandTarget(null);
    setRotatedCommand(null);
    setRotatedPlaintext(null);
    // A rotate rewrote token_hint and cleared last_used_at.
    if (rotated) void load();
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

  /**
   * Enable/disable one client for a token.
   *
   * The Switch is driven by ``token.disabled_clients`` from the list state, so
   * a failed PATCH needs no explicit rollback: the row keeps the server value
   * and the switch snaps back once loading clears.
   */
  const handleToggleClient = async (
    token: MemoryMcpToken,
    client: string,
    enabled: boolean,
  ) => {
    const disabled = new Set(token.disabled_clients ?? []);
    if (enabled) disabled.delete(client);
    else disabled.add(client);
    setTogglingClient(`${token.token_id}:${client}`);
    try {
      await memoryMcpApi.update(token.token_id, {
        // An empty list means "nothing switched off", which the API spells null.
        disabled_clients: disabled.size > 0 ? [...disabled] : null,
      });
      message.success(t("memory.mcp.clientsUpdated", "已更新接入端设置"));
      await load();
    } catch (e) {
      message.error(
        e instanceof Error
          ? e.message
          : t("memory.mcp.clientsUpdateFailed", "更新接入端设置失败，请重试"),
      );
    } finally {
      setTogglingClient(null);
    }
  };

  const renderClients = (token: MemoryMcpToken) => {
    const entries = Object.entries(token.client_stats ?? {});
    if (entries.length === 0) {
      return (
        <Typography.Text type="secondary">
          {t(
            "memory.mcp.clientsEmpty",
            "还没有接入记录（客户端带上 X-Octop-Client 后才会出现）",
          )}
        </Typography.Text>
      );
    }
    const disabled = new Set(token.disabled_clients ?? []);
    return (
      <div style={{ maxWidth: 680 }}>
        <div style={{ ...CLIENT_ROW_STYLE, paddingBottom: 4 }}>
          <Typography.Text type="secondary">
            {t("memory.mcp.clientColumnName", "客户端")}
          </Typography.Text>
          <Typography.Text type="secondary">
            {t("memory.mcp.clientColumnLastSeen", "最近使用")}
          </Typography.Text>
          <Typography.Text type="secondary">
            {t("memory.mcp.clientColumnCount", "次数")}
          </Typography.Text>
          <Typography.Text type="secondary">
            {t("memory.mcp.clientColumnEnabled", "启用")}
          </Typography.Text>
        </div>
        {entries.map(([client, stat]) => (
          <div key={client} style={{ ...CLIENT_ROW_STYLE, padding: "4px 0" }}>
            <Typography.Text strong>{client}</Typography.Text>
            <span>{formatServerIsoDateTime(stat.last_seen, timeZone)}</span>
            <span>{stat.count}</span>
            <span className={styles.clientSwitch}>
              <Switch
                size="small"
                checked={!disabled.has(client)}
                disabled={!!token.revoked_at}
                loading={togglingClient === `${token.token_id}:${client}`}
                aria-label={t(
                  "memory.mcp.clientSwitchLabel",
                  "{{client}} 接入",
                  {
                    client,
                  },
                )}
                onChange={(checked) =>
                  void handleToggleClient(token, client, checked)
                }
              />
            </span>
          </div>
        ))}
      </div>
    );
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
      title: t("memory.mcp.columnExperts", "上报专家"),
      dataIndex: "expert_ids",
      key: "expert_ids",
      render: (_: unknown, token) => {
        const ids = token.expert_ids ?? [];
        if (ids.length === 0) {
          return <Tag>{t("memory.mcp.allExperts", "不限")}</Tag>;
        }
        if (ids.length === 1) {
          const id = ids[0];
          return <Tag title={id}>{expertNames.get(id) ?? id}</Tag>;
        }
        // Historical tokens may still carry several experts; keep them legible
        // without pretending there is a single binding.
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
      title: t("memory.mcp.columnClients", "接入端"),
      key: "clients",
      width: 100,
      render: (_: unknown, token) => {
        const count = Object.keys(token.client_stats ?? {}).length;
        return count > 0 ? (
          <span>{count}</span>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
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
      width: 276,
      render: (_: unknown, token) => (
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            aria-label={t("memory.mcp.command", "接入配置")}
            icon={<Terminal size={14} />}
            disabled={!!token.revoked_at}
            onClick={() => handleCommandClick(token)}
            style={ACTION_TEXT_STYLE}
          >
            {t("memory.mcp.command", "接入配置")}
          </Button>
          <Button
            type="link"
            size="small"
            aria-label={t("memory.mcp.switchExpert", "切换专家")}
            icon={<UserRoundCog size={14} />}
            disabled={!!token.revoked_at}
            onClick={() => openSwitchExpert(token)}
            style={ACTION_TEXT_STYLE}
          >
            {t("memory.mcp.switchExpert", "切换专家")}
          </Button>
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
              type="link"
              size="small"
              aria-label={t("memory.mcp.revoke", "撤销")}
              icon={<Trash2 size={14} />}
              loading={revokingId === token.token_id}
              disabled={!!token.revoked_at}
              style={ACTION_TEXT_STYLE}
            >
              {t("memory.mcp.revoke", "撤销")}
            </Button>
          </Popconfirm>
        </Space>
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
          <h2>{t("memory.mcp.title", "终端接入")}</h2>
          <p>
            {t(
              "memory.mcp.description",
              "外部 Agent（Claude Code / Codex / Cursor / Kiro / DSH）使用这里的 Token 访问 {{endpoint}}。Token 只显示一次，丢失后请重建。",
              { endpoint: "/mcp/memory" },
            )}
            <Typography.Link
              type="secondary"
              href={MCP_SETUP_DOCS_URL}
              target="_blank"
              rel="noreferrer"
              style={{ marginLeft: 8, fontSize: 12 }}
            >
              {t("memory.mcp.docsLink", "接入说明")}
            </Typography.Link>
          </p>
        </div>
        <Button
          type="primary"
          icon={<Plus size={15} />}
          style={{ marginLeft: "auto", flexShrink: 0 }}
          onClick={openCreate}
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
          expandable={{ expandedRowRender: renderClients, columnWidth: 48 }}
          scroll={{ x: 1120 }}
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
                <Button type="primary" onClick={openCreate}>
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
            name="expert_id"
            label={t("memory.mcp.expertsLabel", "上报专家")}
            rules={[
              {
                required: true,
                message: t("memory.mcp.expertRequired", "请选择上报专家"),
              },
            ]}
            extra={t(
              "memory.mcp.expertsHint",
              "Token 绑定哪个专家，通过它上报的记忆就落到哪个专家。",
            )}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={expertPickerOptions}
              placeholder={t("memory.mcp.expertsPlaceholder", "请选择上报专家")}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={switchTarget !== null}
        title={t("memory.mcp.switchExpertTitle", "切换上报专家")}
        okText={t("common.save", "保存")}
        cancelText={t("common.cancel", "取消")}
        confirmLoading={switching}
        onOk={() => void handleSwitchExpert()}
        onCancel={() => {
          if (switching) return;
          setSwitchTarget(null);
          switchForm.resetFields();
        }}
        destroyOnHidden
      >
        {switchTarget ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Typography.Text type="secondary">
              {switchTarget.name}
            </Typography.Text>
            <Form form={switchForm} layout="vertical" requiredMark={false}>
              <Form.Item
                name="expert_id"
                label={t("memory.mcp.expertsLabel", "上报专家")}
                rules={[
                  {
                    required: true,
                    message: t("memory.mcp.expertRequired", "请选择上报专家"),
                  },
                ]}
                extra={t(
                  "memory.mcp.switchExpertHint",
                  "切换后，用该 Token 上报的记忆将落到新的专家；已写入的记忆不会迁移。",
                )}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={expertPickerOptions}
                  placeholder={t(
                    "memory.mcp.switchExpertPlaceholder",
                    "请选择专家",
                  )}
                />
              </Form.Item>
            </Form>
          </Space>
        ) : null}
      </Modal>

      <Modal
        open={created !== null}
        title={t("memory.mcp.plaintextTitle", "Token 已创建")}
        width={780}
        maskClosable={false}
        onCancel={() => setCreated(null)}
        footer={
          <Space>
            <Button
              onClick={() =>
                void copySetupCommand(
                  buildInstallScript(created?.plaintext ?? ""),
                )
              }
              disabled={created === null}
            >
              {t("memory.mcp.copyCommand", "复制命令")}
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
            <Typography.Text type="secondary">
              {t("memory.mcp.tokenLabel", "Token")}
            </Typography.Text>
            <Space.Compact style={{ width: "100%" }}>
              <Input readOnly value={created.plaintext} />
              <Button onClick={() => void handleCopy()}>
                {t("memory.mcp.copyToken", "复制 Token")}
              </Button>
            </Space.Compact>
            <Typography.Text type="secondary">
              {t(
                "memory.mcp.commandReady",
                "请先复制并保存上面的 Token（关闭后无法再次查看）。接入时任选一种方式：",
              )}
            </Typography.Text>
            <Tabs
              size="small"
              items={[
                {
                  key: "unix",
                  label: "macOS / Linux",
                  children: (
                    <Space.Compact style={{ width: "100%" }}>
                      <Input.TextArea
                        readOnly
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        value={buildInstallScript(created.plaintext)}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildInstallScript(created.plaintext),
                          )
                        }
                      >
                        {t("memory.mcp.copyCommand", "复制命令")}
                      </Button>
                    </Space.Compact>
                  ),
                },
                {
                  key: "windows",
                  label: "Windows",
                  children: (
                    <Space.Compact style={{ width: "100%" }}>
                      <Input.TextArea
                        readOnly
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        value={buildInstallPowerShell(created.plaintext)}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildInstallPowerShell(created.plaintext),
                          )
                        }
                      >
                        {t("memory.mcp.copyCommand", "复制命令")}
                      </Button>
                    </Space.Compact>
                  ),
                },
                {
                  key: "ai",
                  label: t("memory.mcp.aiInstall", "交给 AI"),
                  children: (
                    <Space.Compact style={{ width: "100%" }}>
                      <Input.TextArea
                        readOnly
                        autoSize={{ minRows: 4, maxRows: 8 }}
                        value={buildAiPrompt(created.plaintext)}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildAiPrompt(created.plaintext),
                          )
                        }
                      >
                        {t("memory.mcp.copyCommand", "复制命令")}
                      </Button>
                    </Space.Compact>
                  ),
                },
                {
                  key: "json",
                  label: t("memory.mcp.manualConfig", "手动配置"),
                  children: (
                    <Space.Compact style={{ width: "100%" }}>
                      <Input.TextArea
                        readOnly
                        autoSize={{ minRows: 6, maxRows: 12 }}
                        value={buildClientConfig(created.plaintext)}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildClientConfig(created.plaintext),
                          )
                        }
                      >
                        {t("memory.mcp.copyCommand", "复制命令")}
                      </Button>
                    </Space.Compact>
                  ),
                },
              ]}
            />
          </Space>
        ) : null}
      </Modal>

      <Modal
        open={commandTarget !== null}
        title={t("memory.mcp.commandTitle", "重新生成接入命令")}
        width={780}
        okText={t("memory.mcp.commandRegenerate", "重新生成并复制")}
        cancelText={t("common.cancel", "取消")}
        confirmLoading={rotating}
        onOk={() => void handleRegenerateCommand()}
        onCancel={closeCommandModal}
        okButtonProps={{ danger: true }}
        footer={
          rotatedCommand ? (
            <Button type="primary" onClick={closeCommandModal}>
              {t("common.close", "关闭")}
            </Button>
          ) : undefined
        }
        destroyOnHidden
      >
        {commandTarget ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Typography.Text type="secondary">
              {commandTarget.name} · {commandTarget.token_hint}
            </Typography.Text>
            {rotatedCommand ? (
              <>
                <Alert
                  type="warning"
                  showIcon
                  message={t(
                    "memory.mcp.commandRotated",
                    "已重新生成，旧 Token 已失效。请立即复制命令并更新已配置的客户端。",
                  )}
                />
                <Typography.Text type="secondary">
                  {t("memory.mcp.tokenLabel", "Token")}
                </Typography.Text>
                <Space.Compact style={{ width: "100%" }}>
                  <Input readOnly value={rotatedPlaintext ?? ""} />
                  <Button
                    onClick={() => {
                      if (rotatedPlaintext) void copyText(rotatedPlaintext);
                    }}
                  >
                    {t("memory.mcp.copyToken", "复制 Token")}
                  </Button>
                </Space.Compact>
                <Typography.Text type="secondary">
                  {t(
                    "memory.mcp.commandReady",
                    "一键安装命令（已带上这个 Token，可直接粘贴执行）：",
                  )}
                </Typography.Text>
                <Space.Compact style={{ width: "100%" }}>
                  <Input.TextArea
                    readOnly
                    autoSize={{ minRows: 5, maxRows: 12 }}
                    value={rotatedCommand}
                    style={{ fontFamily: "monospace", fontSize: 12 }}
                  />
                  <Button onClick={() => void copySetupCommand(rotatedCommand)}>
                    {t("memory.mcp.copyCommand", "复制命令")}
                  </Button>
                </Space.Compact>
              </>
            ) : (
              <Alert
                type="warning"
                showIcon
                message={t(
                  "memory.mcp.commandMissingWarning",
                  "Token 明文只在创建时显示一次，当前已无法拼出完整命令。重新生成会立即作废旧 Token，需要同步更新已配置的客户端。",
                )}
              />
            )}
          </Space>
        ) : null}
      </Modal>
    </div>
  );
}
