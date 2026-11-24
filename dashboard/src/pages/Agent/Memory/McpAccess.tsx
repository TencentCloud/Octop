/**
 * MCP 接入 — user-level tokens for the memory MCP server.
 *
 * Embedded in the main memory page. External agents authenticate against the
 * Memory MCP endpoint with a plaintext token shown once at creation or rotation.
 */

import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  Alert,
  Button,
  Card,
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
  memorySharingApi,
  type SharingBinding,
  type SharingSession,
  type SharingSpace,
} from "../../../api/modules/memorySharing";
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
import CodexModelSetup from "./CodexModelSetup";
import styles from "./MemorySettings.module.less";

/** Public setup guide for the clients this tab issues tokens to. */
const MCP_SETUP_DOCS_URL =
  "https://github.com/TencentCloud/octop-memory/blob/main/plugins/harness/AI-SETUP.md";
// The installer entry point and the Python package it fetches must use the same revision.
const CODEX_HARNESS_REF = "7260dbaa0e3442fa8a03bf123668f414401d2be6";
const MCP_INSTALL_BASE_URL = `https://raw.githubusercontent.com/TencentCloud/octop-memory/${CODEX_HARNESS_REF}/plugins/harness`;

interface CreateFormValues {
  name: string;
  expert_id?: string;
  access?: "read" | "write";
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

  const [tokenList, setTokenList] = useState<{
    spaceId: string | null;
    tokens: MemoryMcpToken[];
  } | null>(null);
  const [tokenReload, setTokenReload] = useState(0);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<{ detail?: string } | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createExpertDefault, setCreateExpertDefault] = useState<string>("");
  const [createSpaceId, setCreateSpaceId] = useState<string | null>(null);
  const [created, setCreated] = useState<MemoryMcpTokenCreated | null>(null);
  const [codexTarget, setCodexTarget] = useState<MemoryMcpToken | null>(null);
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
  const [sharingSession, setSharingSession] = useState<SharingSession | null>(
    null,
  );
  const [connectCode, setConnectCode] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [changingAuthorization, setChangingAuthorization] = useState(false);
  const [spaces, setSpaces] = useState<SharingSpace[] | null>(null);
  const [spacesError, setSpacesError] = useState(false);
  const [spaceChoice, setSpaceChoice] = useState<string | undefined>();
  const [bindings, setBindings] = useState<Record<string, SharingBinding>>({});
  const [bindingError, setBindingError] = useState<string | null>(null);
  const [savingBinding, setSavingBinding] = useState(false);
  const [form] = Form.useForm<CreateFormValues>();
  const [switchForm] = Form.useForm<SwitchExpertFormValues>();

  const currentExpertId = agents.find(
    (agent) => agent.agent_id === activeAgentId && !agent.bridge,
  )?.agent_id;
  const currentBinding = currentExpertId
    ? bindings[currentExpertId]
    : undefined;
  const scopedSpace =
    sharingSession?.space_id && sharingSession.space_id !== "*"
      ? sharingSession.space_id
      : undefined;
  const suggestedSpace = spaces?.some(
    (space) => space.space_id === currentBinding?.space_id,
  )
    ? currentBinding?.space_id
    : scopedSpace;
  const requestedSpace = spaceChoice ?? suggestedSpace;
  const spaceId = spaces?.some((space) => space.space_id === requestedSpace)
    ? requestedSpace ?? null
    : null;
  const canListTokens = Boolean(
    sharingSession?.connected &&
      spaces &&
      (!currentExpertId ||
        currentBinding ||
        bindingError === currentExpertId) &&
      (spaceId || !scopedSpace),
  );
  const tokens =
    canListTokens && tokenList?.spaceId === spaceId ? tokenList.tokens : [];
  const load = () => setTokenReload((value) => value + 1);

  useEffect(() => {
    void memorySharingApi
      .status()
      .then(setSharingSession)
      .catch(() => setSharingSession({ connected: false }));
  }, []);

  useEffect(() => {
    if (!sharingSession?.connected) return;
    let cancelled = false;
    void memorySharingApi
      .spaces()
      .then(({ spaces }) => {
        if (!cancelled) setSpaces(spaces);
      })
      .catch(() => {
        if (!cancelled) setSpacesError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sharingSession]);

  useEffect(() => {
    if (!currentExpertId) return;
    let cancelled = false;
    void memorySharingApi
      .binding(currentExpertId)
      .then((binding) => {
        if (!cancelled)
          setBindings((value) => ({ ...value, [currentExpertId]: binding }));
      })
      .catch(() => {
        if (!cancelled) setBindingError(currentExpertId);
      });
    return () => {
      cancelled = true;
    };
  }, [currentExpertId]);

  useEffect(() => {
    if (!canListTokens) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    const list = spaceId ? memoryMcpApi.list(spaceId) : memoryMcpApi.list();
    void list
      .then((tokens) => {
        if (!cancelled) setTokenList({ spaceId, tokens });
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setLoadError({ detail: e instanceof Error ? e.message : undefined });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canListTokens, spaceId, tokenReload]);

  const replaceSession = (session: SharingSession) => {
    setSpaces(null);
    setSpacesError(false);
    setSpaceChoice(undefined);
    setTokenList(null);
    setCodexTarget(null);
    setCreated(null);
    setPlaintextByToken({});
    setSharingSession(session);
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      replaceSession(await memorySharingApi.connect(connectCode.trim()));
      setConnectCode("");
      setChangingAuthorization(false);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "连接失败");
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setConnecting(true);
    try {
      replaceSession(await memorySharingApi.disconnect());
    } catch (e) {
      message.error(
        e instanceof Error ? e.message : t("memory.sharing.failed"),
      );
    } finally {
      setConnecting(false);
    }
  };

  const updateBinding = async (target: string | null) => {
    if (!currentExpertId) return;
    setSavingBinding(true);
    try {
      const updated = await memorySharingApi.bind(currentExpertId, target);
      setBindings((value) => ({ ...value, [currentExpertId]: updated }));
      load();
      if (updated.previous_token_revoked === false) {
        message.warning(
          t(
            "memory.sharing.revokePreviousFailed",
            "绑定已更新，但旧专家凭据仍可能有效。请在 Memory 管理端撤销。",
          ),
        );
      }
    } catch (e) {
      message.error(
        e instanceof Error ? e.message : t("memory.sharing.failed"),
      );
    } finally {
      setSavingBinding(false);
    }
  };

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

  /** Default for a new token: the expert the user is looking at right now. */
  const defaultExpertId = useMemo(() => {
    if (expertOptions.some((option) => option.value === activeAgentId)) {
      return activeAgentId as string;
    }
    return expertOptions[0]?.value ?? "";
  }, [expertOptions, activeAgentId]);
  const canCreate = canListTokens && Boolean(spaceId || defaultExpertId);

  const openCreate = () => {
    setCreateExpertDefault(defaultExpertId);
    setCreateSpaceId(spaceId);
    setCreateOpen(true);
  };

  // The create modal is destroyed on close, so the default expert can only be
  // written once its Form is mounted (same commit as ``createOpen``).
  useEffect(() => {
    if (!createOpen) return;
    form.setFieldsValue({ expert_id: createExpertDefault, access: "write" });
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

  const mcpEndpoint = (mcpUrl?: string) =>
    mcpUrl || `${sharingSession?.base_url?.replace(/\/+$/, "") || origin}/mcp/`;

  const buildClientConfig = (plaintext: string, mcpUrl?: string) =>
    JSON.stringify(
      {
        mcpServers: {
          "octop-memory": {
            type: "http",
            url: mcpEndpoint(mcpUrl),
            headers: { Authorization: `Bearer ${plaintext}` },
          },
        },
      },
      null,
      2,
    );

  const buildInstallScript = (plaintext: string, mcpUrl?: string) =>
    `curl -fsSL https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.sh | sh -s -- --url ${mcpEndpoint(
      mcpUrl,
    )} --token ${plaintext}`;

  const buildAiPrompt = (mcpUrl?: string) =>
    [
      "请按 https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/AI-SETUP.md 完成 octop-memory 终端接入。",
      `OCTOP_URL=${mcpEndpoint(mcpUrl)}`,
      t(
        "memory.sharing.localTokenHint",
        "请让我在本机输入 Token，并避免在对话中粘贴凭据。",
      ),
      "安装后按文档里的验证步骤检查召回与上报，并把结果告诉我。",
    ].join("\n");

  const buildCodexPrompt = (token: MemoryMcpToken, codexExtraction: string) =>
    [
      t(
        "memory.mcp.codexPromptIntro",
        "请帮我在本机为 Codex 接入 Octop Memory，使用 MCP 地址 {{endpoint}}。",
        { endpoint: mcpEndpoint(token.mcp_url) },
      ),
      t(
        "memory.mcp.codexPromptInstall",
        "下载并检查官方安装脚本后执行安装。macOS / Linux 使用 {{shellInstaller}}，传入 --url 和 --terminals codex。Windows PowerShell 使用 {{windowsInstaller}}，传入 -Url 和 -Terminals codex。",
        {
          shellInstaller: `${MCP_INSTALL_BASE_URL}/install.sh`,
          windowsInstaller: `${MCP_INSTALL_BASE_URL}/install.ps1`,
        },
      ),
      t(
        "memory.mcp.codexInstallerRef",
        "运行安装器时设置 OCTOP_MEMORY_REF={{ref}}。",
        { ref: CODEX_HARNESS_REF },
      ),
      t(
        "memory.mcp.codexPromptToken",
        "请让我在本机终端以隐藏输入的方式提供本次 Token，通过 OCTOP_MEMORY_TOKEN 传给安装器。仅在我确认接入同一个记忆空间时，才复用同一地址已有的本机凭据。请将 Token 明文留在本机，避免写入对话、命令文本或日志。",
      ),
      token.scopes?.includes("write")
        ? [
            codexExtraction === "codex"
              ? t(
                  "memory.mcp.codexExtractPrompt",
                  "安装前设置 OCTOP_CODEX_EXTRACTION=codex。安装完成后，在发起安装的当前 Codex 对话中，查找本次安装所注册的 MCP 服务下的 memory_propose（包括按需加载的工具）。找到后报告“当前对话已加载 memory_propose”，验证时无需写入候选。仅检查配置文件、服务端工具目录或新开的 Codex 进程，无法确认本对话已加载。若本对话找不到它，报告“已配置，当前对话待重载”，提示打开命令菜单（Mac 按 ⌘K，Windows/Linux 按 Ctrl+K），搜索 MCP，进入 MCP 设置，点击“服务器”标题旁的重启图标。使用 CLI 时退出并恢复原会话。回到同一对话再次检查；若仍不可用，报告实际错误。",
                )
              : codexExtraction.includes("/")
              ? t(
                  "memory.mcp.octopExtractPrompt",
                  "安装前设置 OCTOP_CODEX_EXTRACTION=octop 和 OCTOP_CODEX_REVIEW_URL={{url}}。已为这个 Token 选择 {{model}}，Stop 会在后台由 Octop 复核用户原文。请检查本机 hook 配置的模式和地址。",
                  {
                    model: codexExtraction,
                    url: origin + "/api/memory-mcp/codex-review",
                  },
                )
              : t(
                  "memory.mcp.serverExtractPrompt",
                  "安装前设置 OCTOP_CODEX_EXTRACTION=server。Stop 上报会话，由 Memory 服务配置的模型提取候选。",
                ),
            t(
              "memory.mcp.codexPromptReadWrite",
              "这个 Token 有读写权限。请核对自动召回和会话上报 hooks 已配置，确认 Codex 能发现 memory_get 和 memory_save。用只读操作验证连接，避免写入测试记忆。",
            ),
          ].join("\n")
        : t(
            "memory.mcp.codexPromptReadOnly",
            "这个 Token 只有读取权限。请在运行安装器前设置 OCTOP_CODEX_READ_ONLY=1，核对自动召回已配置，并验证 Codex 能使用 memory_get。",
          ),
      t(
        "memory.mcp.codexPromptResult",
        "完成后请报告验证结果，以及还需我在 Codex 界面完成的重启或 hook 信任操作。",
      ),
    ].join("\n\n");

  const buildInstallPowerShell = (plaintext: string, mcpUrl?: string) =>
    `irm https://raw.githubusercontent.com/TencentCloud/octop-memory/main/plugins/harness/install.ps1 -OutFile install.ps1; .\\install.ps1 -Url ${mcpEndpoint(
      mcpUrl,
    )} -Token ${plaintext}`;

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
        scopes: values.access === "read" ? ["read"] : ["read", "write"],
      };
      if (createSpaceId) body.space_id = createSpaceId;
      else if (values.expert_id) body.expert_ids = [values.expert_id];
      else return;
      const result = await memoryMcpApi.create(body);
      setCreateOpen(false);
      form.resetFields();
      setCreated(result);
      // Keep the secret for this session so the row can copy its command again.
      setPlaintextByToken((prev) => ({
        ...prev,
        [result.token.token_id]: result.plaintext,
      }));
      load();
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
    if (!expertId) return;
    setSwitching(true);
    try {
      await memoryMcpApi.update(switchTarget.token_id, {
        expert_ids: [expertId],
      });
      message.success(t("memory.mcp.switchExpertSuccess", "已切换上报专家"));
      setSwitchTarget(null);
      switchForm.resetFields();
      load();
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
      void copySetupCommand(buildClientConfig(plaintext, token.mcp_url));
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
      const targetSpace = commandTarget.space_id ?? spaceId;
      const result = targetSpace
        ? await memoryMcpApi.rotate(commandTarget.token_id, targetSpace)
        : await memoryMcpApi.rotate(commandTarget.token_id);
      const command = buildClientConfig(result.plaintext, result.token.mcp_url);
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
    if (rotated) load();
  };

  const handleRevoke = async (token: MemoryMcpToken) => {
    setRevokingId(token.token_id);
    try {
      await memoryMcpApi.revoke(token.token_id);
      message.success(t("memory.mcp.revoked", "Token 已撤销"));
      load();
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
      load();
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
    const canToggleClients = !spaceId && Array.isArray(token.disabled_clients);
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
          {canToggleClients && (
            <Typography.Text type="secondary">
              {t("memory.mcp.clientColumnEnabled", "启用")}
            </Typography.Text>
          )}
        </div>
        {entries.map(([client, stat]) => (
          <div key={client} style={{ ...CLIENT_ROW_STYLE, padding: "4px 0" }}>
            <Typography.Text strong>{client}</Typography.Text>
            <span>{formatServerIsoDateTime(stat.last_seen, timeZone)}</span>
            <span>{stat.count}</span>
            {canToggleClients && (
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
            )}
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
      title: t("memory.sharing.scopes", "权限"),
      key: "scopes",
      render: (_: unknown, token) =>
        token.scopes?.length ? (
          <Space size={4} wrap>
            <Tag>
              {token.scopes.includes("write")
                ? t("memory.sharing.readWrite", "读写")
                : t("memory.readOnly", "只读")}
            </Tag>
            {token.scopes.includes("review") && (
              <Tag>{t("memory.sharing.review", "审核")}</Tag>
            )}
          </Space>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
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
          {token.scopes?.includes("write") &&
            token.space_id &&
            !token.revoked_at && (
              <Button
                type="link"
                size="small"
                style={ACTION_TEXT_STYLE}
                onClick={() => setCodexTarget(token)}
              >
                {t("memory.mcp.codexModelSetup", "Codex 提取模型")}
              </Button>
            )}
          {!spaceId && (
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
          )}
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
          <h2>{t("memory.sharing.title", "共享记忆")}</h2>
          <p>
            {t(
              "memory.mcp.description",
              "外部 Agent（Claude Code / Codex / Cursor / Kiro / DSH）使用这里的 Token 访问 {{endpoint}}。Token 只显示一次，丢失后请重建。",
              {
                endpoint:
                  tokens[0]?.mcp_url ||
                  (sharingSession?.base_url
                    ? `${sharingSession.base_url}/mcp/`
                    : "<memory-service>/mcp/"),
              },
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
          disabled={!canCreate}
          onClick={openCreate}
        >
          {t("memory.mcp.create", "创建 Token")}
        </Button>
      </div>

      {sharingSession?.connected === false || changingAuthorization ? (
        <Alert
          type={changingAuthorization ? "info" : "warning"}
          showIcon
          style={{ marginBottom: 12 }}
          message={
            changingAuthorization
              ? t("memory.sharing.changeAuthorization", "更换授权")
              : t("memory.sharing.connectRequired", "连接记忆服务")
          }
          description={
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text>
                {t("memory.sharing.connectHint")}
              </Typography.Text>
              <Space.Compact style={{ width: "100%", maxWidth: 620 }}>
                <Input
                  aria-label={t("memory.sharing.codeLabel", "一次性授权码")}
                  value={connectCode}
                  onChange={(event) => setConnectCode(event.target.value)}
                  placeholder="mcode_…"
                />
                <Button
                  type="primary"
                  loading={connecting}
                  disabled={!connectCode.trim()}
                  onClick={() => void handleConnect()}
                >
                  {t("memory.mcp.connect", "连接")}
                </Button>
              </Space.Compact>
            </Space>
          }
        />
      ) : null}

      {sharingSession?.connected && (
        <Card size="small" className={styles.settingCard}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>
              <Tag color="success">
                {t("memory.sharing.serviceConnected", "记忆服务已连接")}
              </Tag>
              {scopedSpace && (
                <Typography.Text type="secondary">
                  {t("memory.sharing.connectedTo", "当前空间：{{space}}", {
                    space: scopedSpace,
                  })}
                </Typography.Text>
              )}
              <Button
                size="small"
                disabled={connecting}
                aria-expanded={changingAuthorization}
                onClick={() => setChangingAuthorization((value) => !value)}
              >
                {t("memory.sharing.changeAuthorization", "更换授权")}
              </Button>
              <Button
                size="small"
                loading={connecting}
                onClick={() => void handleDisconnect()}
              >
                {t("memory.sharing.disconnectSession", "断开管理会话")}
              </Button>
            </Space>
            <Space wrap align="end">
              <Space direction="vertical" size={4}>
                <label htmlFor="shared-memory-space">
                  {t("memory.sharing.spaceLabel", "管理空间")}
                </label>
                <Select
                  id="shared-memory-space"
                  value={spaceId || (!scopedSpace && spaces ? "" : undefined)}
                  options={[
                    ...(!scopedSpace
                      ? [
                          {
                            value: "",
                            label: t(
                              "memory.sharing.defaultSpace",
                              "专家默认空间",
                            ),
                          },
                        ]
                      : []),
                    ...(spaces ?? []).map((space) => ({
                      value: space.space_id,
                      label:
                        space.display_name &&
                        space.display_name !== space.space_id
                          ? `${space.display_name} · ${space.space_id}`
                          : space.space_id,
                    })),
                  ]}
                  loading={!spaces && !spacesError}
                  disabled={!spaces || savingBinding}
                  placeholder={t("memory.sharing.spaceLabel", "管理空间")}
                  onChange={setSpaceChoice}
                  style={{ width: 260 }}
                />
              </Space>
              {currentExpertId && currentBinding?.can_manage !== false && (
                <Button
                  loading={savingBinding}
                  disabled={!spaceId || !currentBinding}
                  onClick={() => {
                    if (spaceId) void updateBinding(spaceId);
                  }}
                >
                  {spaceId && currentBinding?.space_id === spaceId
                    ? t("memory.sharing.reauthorize", "重新授权当前专家")
                    : t("memory.sharing.bind", "绑定当前专家")}
                </Button>
              )}
              {currentExpertId &&
                currentBinding?.space_id &&
                currentBinding.can_manage !== false && (
                  <Popconfirm
                    title={t(
                      "memory.sharing.unbindConfirm",
                      "解除当前专家的共享空间绑定？",
                    )}
                    onConfirm={() => updateBinding(null)}
                  >
                    <Button disabled={savingBinding}>
                      {t("memory.sharing.unbind", "解除绑定")}
                    </Button>
                  </Popconfirm>
                )}
            </Space>
            {currentExpertId && (
              <Typography.Text type="secondary">
                {t("memory.sharing.currentExpert", "当前专家：{{expert}}", {
                  expert: expertNames.get(currentExpertId) ?? currentExpertId,
                })}
                {" · "}
                {currentBinding?.space_id
                  ? t("memory.sharing.currentBinding", "已绑定 {{space}}", {
                      space: currentBinding.space_id,
                    })
                  : t("memory.sharing.unbound", "当前专家尚未绑定空间")}
              </Typography.Text>
            )}
            {currentBinding?.space_id &&
              currentBinding.has_credential === false && (
                <Alert
                  type="warning"
                  showIcon
                  message={t(
                    "memory.sharing.expertCredentialMissing",
                    "专家尚无共享空间凭据。选择该空间并重新绑定以签发专家凭据。",
                  )}
                />
              )}
            {spacesError && (
              <Alert
                type="error"
                showIcon
                message={t(
                  "memory.sharing.spacesFailed",
                  "记忆空间加载失败，请刷新后重试。",
                )}
              />
            )}
            {bindingError === currentExpertId && (
              <Alert
                type="error"
                showIcon
                message={t(
                  "memory.sharing.bindingFailed",
                  "专家空间绑定加载失败。",
                )}
              />
            )}
          </Space>
        </Card>
      )}

      {canListTokens && loadError ? (
        <Alert
          type="error"
          showIcon
          message={
            loadError.detail ?? t("memory.mcp.loadFailed", "Token 列表加载失败")
          }
          action={
            <Button size="small" onClick={load}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      ) : null}

      {!sharingSession || (canListTokens && loading && tokens.length === 0) ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : canListTokens ? (
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
                <Button
                  type="primary"
                  disabled={!canCreate}
                  onClick={openCreate}
                >
                  {t("memory.mcp.create", "创建 Token")}
                </Button>
              </Empty>
            ),
          }}
        />
      ) : null}

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
          {createSpaceId ? (
            <Form.Item label={t("memory.sharing.spaceLabel", "管理空间")}>
              <Typography.Text code>{createSpaceId}</Typography.Text>
            </Form.Item>
          ) : (
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
                options={expertOptions}
                placeholder={t(
                  "memory.mcp.expertsPlaceholder",
                  "请选择上报专家",
                )}
              />
            </Form.Item>
          )}
          <Form.Item
            name="access"
            label={t("memory.sharing.scopes", "权限")}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: "read", label: t("memory.readOnly", "只读") },
                {
                  value: "write",
                  label: t("memory.sharing.readWrite", "读写"),
                },
              ]}
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
                  options={expertOptions}
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
        open={codexTarget !== null}
        title={t("memory.mcp.codexModelSetup", "Codex 提取模型")}
        footer={null}
        onCancel={() => setCodexTarget(null)}
        destroyOnHidden
      >
        {codexTarget && (
          <CodexModelSetup
            key={codexTarget.token_id}
            token={codexTarget}
            prompt={buildCodexPrompt}
            copy={copySetupCommand}
          />
        )}
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
                  buildInstallScript(
                    created?.plaintext ?? "",
                    created?.token.mcp_url,
                  ),
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
                        value={buildInstallScript(
                          created.plaintext,
                          created.token.mcp_url,
                        )}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildInstallScript(
                              created.plaintext,
                              created.token.mcp_url,
                            ),
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
                        value={buildInstallPowerShell(
                          created.plaintext,
                          created.token.mcp_url,
                        )}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildInstallPowerShell(
                              created.plaintext,
                              created.token.mcp_url,
                            ),
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
                        value={buildAiPrompt(created.token.mcp_url)}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildAiPrompt(created.token.mcp_url),
                          )
                        }
                      >
                        {t("memory.mcp.copyCommand", "复制命令")}
                      </Button>
                    </Space.Compact>
                  ),
                },
                {
                  key: "codex",
                  label: t("memory.mcp.codexPromptLabel", "Codex 接入提示词"),
                  children: (
                    <CodexModelSetup
                      key={created.token.token_id}
                      token={created.token}
                      prompt={buildCodexPrompt}
                      copy={copySetupCommand}
                    />
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
                        value={buildClientConfig(
                          created.plaintext,
                          created.token.mcp_url,
                        )}
                        style={{ fontFamily: "monospace", fontSize: 12 }}
                      />
                      <Button
                        onClick={() =>
                          void copySetupCommand(
                            buildClientConfig(
                              created.plaintext,
                              created.token.mcp_url,
                            ),
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
