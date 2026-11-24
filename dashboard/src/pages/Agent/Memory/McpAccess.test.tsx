import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryMcp", () => ({
  memoryMcpApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    revoke: vi.fn(),
    rotate: vi.fn(),
  },
}));

vi.mock("../../../api/modules/memorySharing", () => ({
  memorySharingApi: {
    status: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    spaces: vi.fn(),
    binding: vi.fn(),
    bind: vi.fn(),
  },
}));

vi.mock("../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));

vi.mock("../../../utils/copyText", () => ({
  copyText: vi.fn().mockResolvedValue(true),
}));

// Token expert ids are agent ids, so the page reads the agent list. Two local
// experts are enough to exercise the single-select and the default binding.
vi.mock("../../../context/AgentContext", () => {
  const agents = [
    { agent_id: "agent_a", name: "专家甲", bridge: false },
    { agent_id: "agent_b", name: "专家乙", bridge: false },
  ];
  return {
    useAgent: () => ({
      agents,
      activeAgentId: "agent_b",
      activeAgent: null,
      loading: false,
      error: null,
      setActiveAgent: () => undefined,
      refresh: async () => undefined,
    }),
  };
});

import {
  memoryMcpApi,
  type MemoryMcpToken,
} from "../../../api/modules/memoryMcp";
import { memorySharingApi } from "../../../api/modules/memorySharing";
import { message } from "../../../utils/antdMessage";
import { copyText } from "../../../utils/copyText";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import McpAccess from "./McpAccess";

const api = vi.mocked(memoryMcpApi, true);
const copyMock = vi.mocked(copyText);

/** Memory resolves a token's space from its bearer credential. */
function clientConfig(
  plaintext: string,
  url = `${window.location.origin}/mcp/`,
): string {
  return JSON.stringify(
    {
      mcpServers: {
        "octop-memory": {
          type: "http",
          url,
          headers: { Authorization: `Bearer ${plaintext}` },
        },
      },
    },
    null,
    2,
  );
}

const activeToken: MemoryMcpToken = {
  token_id: "tok_1",
  name: "codex@macbook",
  expert_ids: null,
  token_hint: "omcp_…abcd",
  created_at: "2026-11-09T08:00:00Z",
  last_used_at: null,
  revoked_at: null,
  disabled_clients: null,
  client_stats: null,
};

/** Two clients reported through ``X-Octop-Client``; both currently allowed. */
const clientToken: MemoryMcpToken = {
  ...activeToken,
  token_id: "tok_clients",
  name: "claude@laptop",
  disabled_clients: [],
  client_stats: {
    "claude-code": {
      first_seen: "2026-11-09T10:00:00Z",
      last_seen: "2026-11-10T09:30:00Z",
      count: 42,
    },
    codex: {
      first_seen: "2026-11-09T11:00:00Z",
      last_seen: "2026-11-09T12:00:00Z",
      count: 3,
    },
  },
};

/** antd's expand toggle renders as a button with a locale aria-label. */
function expandButtons(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(".ant-table-row-expand-icon"),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue([activeToken]);
  vi.mocked(memorySharingApi.status).mockResolvedValue({ connected: true });
  vi.mocked(memorySharingApi.spaces).mockResolvedValue({ spaces: [] });
  vi.mocked(memorySharingApi.binding).mockResolvedValue({
    agent_id: "agent_b",
    space_id: null,
  });
});

describe("<McpAccess />", () => {
  it("shows the connected MCP address before the first token is created", async () => {
    api.list.mockResolvedValue([]);
    vi.mocked(memorySharingApi.status).mockResolvedValue({
      connected: true,
      base_url: "http://127.0.0.1:8088",
    });

    render(<McpAccess />);

    expect(await screen.findByText(/127\.0\.0\.1:8088\/mcp\//)).toBeVisible();
  });

  it("replaces the active management authorization without disconnecting first", async () => {
    vi.mocked(memorySharingApi.connect).mockResolvedValue({
      connected: true,
      space_id: "project-alpha",
    });
    vi.mocked(memorySharingApi.spaces).mockResolvedValue({
      spaces: [{ space_id: "project-alpha" }],
    });
    const user = userEvent.setup();
    render(<McpAccess />);

    await user.click(await screen.findByRole("button", { name: "更换授权" }));
    await user.type(
      screen.getByRole("textbox", { name: "一次性授权码" }),
      "mcode_test",
    );
    await user.click(screen.getByRole("button", { name: /^连\s*接$/ }));

    expect(memorySharingApi.connect).toHaveBeenCalledWith("mcode_test");
    expect(memorySharingApi.disconnect).not.toHaveBeenCalled();
    expect(await screen.findByText("当前空间：project-alpha")).toBeVisible();
    await waitFor(() => expect(api.list).toHaveBeenCalledWith("project-alpha"));
  });

  it("renders the token hint, unscoped experts and active status", async () => {
    render(<McpAccess />);

    expect(await screen.findByText("codex@macbook")).toBeInTheDocument();
    expect(screen.getByText("omcp_…abcd")).toBeInTheDocument();
    expect(screen.getByText("不限")).toBeInTheDocument();
    expect(screen.getByText("有效")).toBeInTheDocument();
    expect(screen.getByText("从未使用")).toBeInTheDocument();
    expect(api.list).toHaveBeenCalledTimes(1);
  });

  it("shows the bound expert name, and a count for multi-expert tokens", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, token_id: "tok_single", expert_ids: ["agent_b"] },
      {
        ...activeToken,
        token_id: "tok_multi",
        expert_ids: ["agent_a", "agent_b"],
      },
    ]);
    render(<McpAccess />);

    // Single binding renders the expert name; the historical multi-expert row
    // renders a count plus one tag per expert.
    await waitFor(() => expect(screen.getAllByText("专家乙")).toHaveLength(2));
    expect(screen.getByText("专家甲")).toBeInTheDocument();
    expect(screen.getByText("2 个专家")).toBeInTheDocument();
  });

  it("shows the one-time plaintext after creating a token", async () => {
    api.create.mockResolvedValue({
      token: {
        ...activeToken,
        token_id: "tok_2",
        name: "claude@laptop",
      },
      plaintext: "omcp_live_plaintext_value",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");

    await user.click(screen.getByRole("button", { name: /创建 Token/ }));
    const nameInput = await screen.findByRole("textbox", { name: "名称" });
    await user.type(nameInput, "claude@laptop");
    // The expert picker defaults to the expert currently in view and stays
    // single-select; re-pick another one to prove the value is sent.
    expect(await screen.findByText("专家乙 · agent_b")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "上报专家" }));
    await user.click(await screen.findByTitle("专家甲 · agent_a"));
    await user.click(screen.getByRole("button", { name: /^创\s*建$/ }));

    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith({
        name: "claude@laptop",
        expert_ids: ["agent_a"],
        scopes: ["read", "write"],
      }),
    );
    expect(
      await screen.findByDisplayValue("omcp_live_plaintext_value"),
    ).toBeInTheDocument();
    expect(screen.getByText(/只显示这一次/)).toBeInTheDocument();
    // The list is refreshed after a successful create.
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  });

  it("signs a read-only client token for the selected space without binding the expert", async () => {
    vi.mocked(memorySharingApi.spaces).mockResolvedValue({
      spaces: [{ space_id: "project-alpha", display_name: "Alpha" }],
    });
    api.create.mockResolvedValue({
      token: {
        ...activeToken,
        name: "codex-alpha",
        space_id: "project-alpha",
        scopes: ["read"],
        mcp_url: "https://memory.example/mcp/",
      },
      plaintext: "omcp_scoped_token",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");
    await user.click(screen.getByRole("combobox", { name: "管理空间" }));
    await user.click(await screen.findByTitle("Alpha · project-alpha"));

    await waitFor(() => expect(api.list).toHaveBeenCalledWith("project-alpha"));
    expect(memorySharingApi.bind).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /创建 Token/ }));
    await user.type(
      await screen.findByRole("textbox", { name: "名称" }),
      "codex-alpha",
    );
    await user.click(screen.getByRole("combobox", { name: "权限" }));
    await user.click(await screen.findByTitle("只读"));
    await user.click(screen.getByRole("button", { name: /^创\s*建$/ }));

    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith({
        name: "codex-alpha",
        space_id: "project-alpha",
        scopes: ["read"],
      }),
    );
    await user.click(await screen.findByRole("tab", { name: "手动配置" }));
    const manualConfig = await screen.findByRole("tabpanel", {
      name: "手动配置",
    });
    expect(within(manualConfig).getByRole("textbox")).toHaveValue(
      clientConfig("omcp_scoped_token", "https://memory.example/mcp/"),
    );
  });

  it("binds the current expert separately from the client list", async () => {
    vi.mocked(memorySharingApi.spaces).mockResolvedValue({
      spaces: [{ space_id: "project-alpha", display_name: "Alpha" }],
    });
    vi.mocked(memorySharingApi.bind).mockResolvedValue({
      agent_id: "agent_b",
      space_id: "project-alpha",
      has_credential: true,
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");
    await user.click(screen.getByRole("combobox", { name: "管理空间" }));
    await user.click(await screen.findByTitle("Alpha · project-alpha"));
    await user.click(screen.getByRole("button", { name: "绑定当前专家" }));

    expect(memorySharingApi.bind).toHaveBeenCalledWith(
      "agent_b",
      "project-alpha",
    );
    expect(
      await screen.findByText(/当前专家：专家乙.*已绑定 project-alpha/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "重新授权当前专家" }));
    expect(memorySharingApi.bind).toHaveBeenCalledTimes(2);
    expect(api.create).not.toHaveBeenCalled();
  });

  it("switches the reporting expert via PATCH and refreshes the list", async () => {
    api.update.mockResolvedValue({ ...activeToken, expert_ids: ["agent_a"] });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");

    await user.click(screen.getByRole("button", { name: /切换专家/ }));
    await user.click(await screen.findByRole("combobox", { name: "上报专家" }));
    await user.click(await screen.findByTitle("专家甲 · agent_a"));
    await user.click(screen.getByRole("button", { name: /^保\s*存$/ }));

    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("tok_1", {
        expert_ids: ["agent_a"],
      }),
    );
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
    expect(message.success).toHaveBeenCalledWith("已切换上报专家");
  });

  it("revokes a token via the confirmation and refreshes the list", async () => {
    api.revoke.mockResolvedValue({ revoked: true });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");

    await user.click(screen.getByRole("button", { name: /撤\s*销/ }));
    // The Popconfirm's ok button shares the "撤销" label; the last one is it.
    const revokeButtons = await screen.findAllByRole("button", {
      name: /撤\s*销/,
    });
    await user.click(revokeButtons[revokeButtons.length - 1]);

    await waitFor(() => expect(api.revoke).toHaveBeenCalledWith("tok_1"));
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  });

  it("shows the revoked state and disables row actions for revoked tokens", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, revoked_at: "2026-11-09T09:00:00Z" },
    ]);
    render(<McpAccess />);

    expect(await screen.findByText("已撤销")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /撤\s*销/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /切换专家/ })).toBeDisabled();
  });

  it("expands a token to show each client's name, last use and call count", async () => {
    api.list.mockResolvedValue([clientToken]);
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("claude@laptop");

    // The 接入端 column counts the distinct clients, before any expansion.
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("claude-code")).not.toBeInTheDocument();

    await user.click(expandButtons(container)[0]);

    expect(await screen.findByText("claude-code")).toBeInTheDocument();
    expect(screen.getByText("codex")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    // last_seen is rendered in the server timezone, not the viewer's.
    expect(
      screen.getByText(
        formatServerIsoDateTime("2026-11-10T09:30:00Z", "Asia/Shanghai"),
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("switch")).toHaveLength(2);
    expect(screen.getByRole("switch", { name: "codex 接入" })).toBeChecked();
  });

  it("turns a client off through PATCH and refreshes the list", async () => {
    api.list.mockResolvedValue([clientToken]);
    api.update.mockResolvedValue({
      ...clientToken,
      disabled_clients: ["codex"],
    });
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("claude@laptop");
    await user.click(expandButtons(container)[0]);

    await user.click(await screen.findByRole("switch", { name: "codex 接入" }));

    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("tok_clients", {
        disabled_clients: ["codex"],
      }),
    );
    expect(message.success).toHaveBeenCalledWith("已更新接入端设置");
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  });

  it("shows usage without unsupported switches for Memory-issued client tokens", async () => {
    api.list.mockResolvedValue([{ ...clientToken, disabled_clients: null }]);
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("claude@laptop");
    await user.click(expandButtons(container)[0]);

    expect(await screen.findByText("codex")).toBeVisible();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it("sends disabled_clients: null when the last switched-off client is re-enabled", async () => {
    api.list.mockResolvedValue([
      { ...clientToken, disabled_clients: ["codex"] },
    ]);
    api.update.mockResolvedValue(clientToken);
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("claude@laptop");
    await user.click(expandButtons(container)[0]);

    const codexSwitch = await screen.findByRole("switch", {
      name: "codex 接入",
    });
    expect(codexSwitch).not.toBeChecked();
    expect(
      screen.getByRole("switch", { name: "claude-code 接入" }),
    ).toBeChecked();
    await user.click(codexSwitch);

    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("tok_clients", {
        disabled_clients: null,
      }),
    );
  });

  it("disables the client switches of a revoked token", async () => {
    api.list.mockResolvedValue([
      { ...clientToken, revoked_at: "2026-11-09T09:00:00Z" },
    ]);
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("claude@laptop");
    await user.click(expandButtons(container)[0]);

    const switches = await screen.findAllByRole("switch");
    expect(switches).toHaveLength(2);
    for (const control of switches) expect(control).toBeDisabled();
  });

  it("explains the empty client list until a client sends its header", async () => {
    const user = userEvent.setup();
    const { container } = render(<McpAccess />);
    await screen.findByText("codex@macbook");

    await user.click(expandButtons(container)[0]);

    expect(
      await screen.findByText(
        "还没有接入记录（客户端带上 X-Octop-Client 后才会出现）",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    { scopes: ["read", "write"], expected: "memory_save" },
    { scopes: ["read"], expected: "OCTOP_CODEX_READ_ONLY=1" },
  ])(
    "copies a Codex setup prompt for token scopes $scopes",
    async ({ scopes, expected }) => {
      const endpoint = "https://memory.example.com/mcp/";
      const plaintext = "omcp_test_prompt_secret";
      api.create.mockResolvedValue({
        token: { ...activeToken, mcp_url: endpoint, scopes },
        plaintext,
      });
      const user = userEvent.setup();
      render(<McpAccess />);

      await screen.findByText("codex@macbook");
      await user.click(screen.getByRole("button", { name: /创建 Token/ }));
      await user.type(
        await screen.findByRole("textbox", { name: "名称" }),
        "Codex",
      );
      await user.click(screen.getByRole("button", { name: /^创\s*建$/ }));
      await user.click(
        await screen.findByRole("tab", { name: "Codex 接入提示词" }),
      );

      const prompt = screen.getByRole<HTMLTextAreaElement>("textbox", {
        name: "Codex 接入提示词",
      }).value;
      expect(prompt).toContain(endpoint);
      expect(prompt).toContain("--terminals codex");
      expect(prompt).toContain("OCTOP_MEMORY_TOKEN");
      expect(prompt).toContain("memory_get");
      expect(prompt).toContain(expected);
      if (!scopes.includes("write"))
        expect(prompt).not.toContain("memory_save");
      expect(prompt).not.toContain(plaintext);

      await user.click(screen.getByRole("button", { name: "复制提示词" }));
      expect(copyMock).toHaveBeenCalledWith(prompt);
      if (scopes.includes("write")) {
        expect(prompt).toContain("OCTOP_CODEX_EXTRACTION=codex");
        expect(prompt).toContain("memory_propose");
        expect(prompt).toContain("当前 Codex 对话");
        expect(prompt).toContain("当前对话待重载");
        expect(prompt).toContain("⌘K");
        expect(prompt).toContain("回到同一对话再次检查");
        await user.click(
          screen.getByRole("combobox", { name: "记忆提取模型" }),
        );
        await user.click(screen.getByText("Memory 服务配置的模型"));
        const serverPrompt = screen.getByRole<HTMLTextAreaElement>("textbox", {
          name: "Codex 接入提示词",
        }).value;
        expect(serverPrompt).toContain("OCTOP_CODEX_EXTRACTION=server");
        expect(serverPrompt).not.toContain("memory_propose");
      } else {
        expect(prompt).not.toContain("memory_propose");
        expect(
          screen.queryByRole("combobox", { name: "记忆提取模型" }),
        ).toBeNull();
      }
    },
  );

  it("copies a token's setup command straight away while its plaintext is cached", async () => {
    const freshToken: MemoryMcpToken = {
      ...activeToken,
      token_id: "tok_2",
      name: "claude@laptop",
    };
    api.list.mockResolvedValue([activeToken, freshToken]);
    api.create.mockResolvedValue({
      token: freshToken,
      plaintext: "omcp_live_plaintext_value",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");

    // Creating a token is what puts the plaintext in the session cache.
    await user.click(screen.getByRole("button", { name: /创建 Token/ }));
    await user.type(
      await screen.findByRole("textbox", { name: "名称" }),
      "claude@laptop",
    );
    await user.click(screen.getByRole("button", { name: /^创\s*建$/ }));
    await screen.findByDisplayValue("omcp_live_plaintext_value");
    await user.click(screen.getByRole("button", { name: "我已保存，关闭" }));

    // The second row (claude@laptop) is the one with a cached plaintext.
    const commandButtons = await screen.findAllByRole("button", {
      name: /接入配置/,
    });
    await user.click(commandButtons[1]);

    await waitFor(() =>
      expect(copyMock).toHaveBeenCalledWith(
        clientConfig("omcp_live_plaintext_value"),
      ),
    );
    expect(message.success).toHaveBeenCalledWith("已复制");
    // No modal and no regeneration: the plaintext was still known.
    expect(api.rotate).not.toHaveBeenCalled();
    expect(
      screen.queryByText(/明文只在创建时显示一次/),
    ).not.toBeInTheDocument();
  });

  it("regenerates the token before copying when the plaintext is unknown", async () => {
    api.rotate.mockResolvedValue({
      token: { ...activeToken, token_hint: "omcp_…new0" },
      plaintext: "omcp_rotated_secret",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await screen.findByText("codex@macbook");

    await user.click(screen.getByRole("button", { name: /接入配置/ }));
    expect(
      await screen.findByText(/明文只在创建时显示一次/),
    ).toBeInTheDocument();
    expect(api.rotate).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /重新生成并复制/ }));

    await waitFor(() => expect(api.rotate).toHaveBeenCalledWith("tok_1"));
    await waitFor(() =>
      expect(copyMock).toHaveBeenCalledWith(
        clientConfig("omcp_rotated_secret"),
      ),
    );
    // The new config stays on screen so it can be copied again.
    await waitFor(() => {
      const areas = Array.from(document.querySelectorAll("textarea"));
      expect(
        areas.some(
          (area) => area.value === clientConfig("omcp_rotated_secret"),
        ),
      ).toBe(true);
    });
    expect(screen.getByText(/旧 Token 已失效/)).toBeInTheDocument();

    // Closing the modal refreshes the list (token_hint changed server-side).
    await user.click(screen.getByRole("button", { name: /关\s*闭/ }));
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  });

  it("disables the setup-command action of a revoked token", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, revoked_at: "2026-11-09T09:00:00Z" },
    ]);
    render(<McpAccess />);

    expect(await screen.findByText("已撤销")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /接入配置/ })).toBeDisabled();
  });
});
