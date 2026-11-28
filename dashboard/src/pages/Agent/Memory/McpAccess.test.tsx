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
    getCodexModel: vi.fn(),
    getCodexStatus: vi.fn(),
    setCodexModel: vi.fn(),
  },
}));

vi.mock("../../../api/modules/provider", () => ({
  providerApi: {
    listResolvedModels: vi.fn().mockResolvedValue([
      { provider_name: "lab", model: "review", name: "Review" },
      { provider_name: "lab", model: "small", name: "Small" },
    ]),
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
import McpAccess from "./McpAccess";

const api = vi.mocked(memoryMcpApi, true);
const copyMock = vi.mocked(copyText);

/** Memory resolves a token's space from its bearer credential. */
function clientConfig(url = `${window.location.origin}/mcp/`): string {
  return JSON.stringify(
    {
      mcpServers: {
        "octop-memory": {
          type: "http",
          url,
          headers: { Authorization: "Bearer <TOKEN>" },
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
  client_stats: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getCodexModel.mockResolvedValue({ model: null, mode: "codex" });
  api.getCodexStatus.mockResolvedValue({ observed: null, last_run: null });
  api.setCodexModel.mockImplementation(async (_id, _space, model, mode) => ({
    model,
    mode,
  }));
  api.list.mockResolvedValue([activeToken]);
  vi.mocked(memorySharingApi.status).mockResolvedValue({ connected: true });
  vi.mocked(memorySharingApi.spaces).mockResolvedValue({ spaces: [] });
  vi.mocked(memorySharingApi.binding).mockResolvedValue({
    agent_id: "agent_b",
    space_id: null,
  });
});

describe("<McpAccess />", () => {
  it("loads and saves an existing Codex token's Octop extraction model", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, scopes: ["read", "write"], space_id: "work" },
    ]);
    api.getCodexModel.mockResolvedValue({ model: null });
    api.setCodexModel.mockResolvedValue({
      model: "lab/review",
      published_at: "2026-11-25T03:00:00Z",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await user.click(
      await screen.findByRole("button", { name: "Codex 提取模型" }),
    );
    await user.click(
      await screen.findByRole("combobox", { name: "记忆提取模型" }),
    );
    await user.click(await screen.findByTitle("lab / Review"));
    expect(api.setCodexModel).not.toHaveBeenCalled();
    expect(await screen.findByText("所选配置尚未应用")).toBeVisible();
    expect(screen.getByText(/先点击「应用到终端」/)).toBeVisible();
    expect(
      screen.getByText(/发布后请重新点击「配置本机 Codex」/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "配置本机 Codex" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "应用到终端" }));
    expect(api.setCodexModel).toHaveBeenCalledWith(
      "tok_1",
      "work",
      "lab/review",
      undefined,
      true,
    );
    expect(
      screen.queryByRole("textbox", { name: "Codex 接入提示词" }),
    ).toBeNull();
    expect(screen.queryByText("查看完整指令")).toBeNull();
    expect(screen.queryByRole("button", { name: "复制提示词" })).toBeNull();
    expect(await screen.findByText("等待终端确认")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "配置本机 Codex" }),
    ).toBeEnabled();
    await user.click(screen.getByRole("combobox", { name: "记忆提取模型" }));
    await user.click(await screen.findByTitle("跟随当前 Codex 会话"));
    await user.click(screen.getByRole("button", { name: "应用到终端" }));
    expect(api.setCodexModel).toHaveBeenCalledWith(
      "tok_1",
      "work",
      null,
      undefined,
      true,
    );
  });

  it("keeps setup instructions separate when switching between Octop models", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, scopes: ["read", "write"], space_id: "work" },
    ]);
    api.getCodexModel.mockResolvedValue({ model: "lab/review" });
    api.getCodexStatus.mockResolvedValue({
      observed: { mode: "octop", timestamp: "2026-11-25T03:00:00Z" },
      last_run: {
        mode: "octop",
        model: "lab/review",
        timestamp: "2026-11-25T03:00:00Z",
      },
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await user.click(
      await screen.findByRole("button", { name: "Codex 提取模型" }),
    );
    await waitFor(() => expect(screen.getByText("lab / Review")).toBeVisible());
    await user.click(screen.getByRole("combobox", { name: "记忆提取模型" }));
    await user.click(await screen.findByTitle("lab / Small"));
    await user.click(screen.getByRole("button", { name: "应用到终端" }));
    expect(api.setCodexModel).toHaveBeenCalledWith(
      "tok_1",
      "work",
      "lab/small",
      undefined,
      true,
    );
    expect(await screen.findByText("终端已确认")).toBeVisible();
    expect(screen.queryByRole("button", { name: "复制提示词" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "配置本机 Codex" }));
    expect(
      await screen.findByRole("dialog", { name: "配置本机 Codex" }),
    ).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "记忆提取模型" })).toBeNull();
    const details = screen.getByText("查看完整指令");
    expect(details.closest("details")).not.toHaveAttribute("open");
    await user.click(screen.getByRole("button", { name: "复制提示词" }));
    expect(copyMock).toHaveBeenCalledWith(
      expect.stringContaining("OCTOP_CODEX_PANEL_SYNC=1"),
    );
    await user.click(details);
    const prompt = screen.getByRole<HTMLTextAreaElement>("textbox", {
      name: "Codex 接入提示词",
    });
    expect(prompt.value).toContain("v1.0.7");
    expect(prompt.value).toContain("/api/memory-mcp/codex-review");
    expect(api.rotate).not.toHaveBeenCalled();
  });

  it("keeps a saved model pending on reopen until the credential reports the new mode", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, space_id: "work", scopes: ["read", "write"] },
    ]);
    api.getCodexModel.mockResolvedValue({
      model: "lab/review",
      mode_since: "2026-11-25T03:00:00Z",
      published_at: "2026-11-25T03:00:00Z",
    });
    const oldRun = {
      mode: "codex" as const,
      model: "astra",
      timestamp: "2026-11-25T02:00:00Z",
    };
    api.getCodexStatus.mockResolvedValue({
      observed: oldRun,
      last_run: oldRun,
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await user.click(
      await screen.findByRole("button", { name: "Codex 提取模型" }),
    );
    await waitFor(() => expect(screen.getByText("等待终端确认")).toBeVisible());
    expect(await screen.findByText("astra")).toBeVisible();
    api.getCodexStatus.mockResolvedValue({
      observed: { mode: "octop", timestamp: "2026-11-25T01:00:00Z" },
      last_run: oldRun,
    });
    await user.click(screen.getByRole("button", { name: "刷新终端状态" }));
    expect(
      await screen.findByText(/最近运行方式：Octop 委托复核/),
    ).toBeVisible();
    expect(screen.getByText("等待终端确认")).toBeVisible();
    api.getCodexStatus.mockResolvedValue({
      observed: { mode: "octop", timestamp: "2026-11-25T04:00:00Z" },
      acknowledgement: {
        revision: "2026-11-25T03:00:00Z",
        timestamp: "2026-11-25T04:00:00Z",
      },
      last_run: oldRun,
    });
    await user.click(screen.getByRole("button", { name: "刷新终端状态" }));
    expect(await screen.findByText("终端已确认")).toBeVisible();
    expect(screen.getByText("astra")).toBeVisible();
  });

  it("uses the paired hook installer and preserves the local mode until published", async () => {
    vi.stubEnv(
      "VITE_CODEX_HARNESS_WHEEL",
      "/assets/test/installer.whl#sha256=test",
    );
    try {
      api.list.mockResolvedValue([
        { ...activeToken, space_id: "work", scopes: ["read", "write"] },
      ]);
      api.getCodexModel.mockResolvedValue({ model: "lab/review" });
      const user = userEvent.setup();
      render(<McpAccess />);
      await user.click(
        await screen.findByRole("button", { name: "Codex 提取模型" }),
      );
      await user.click(
        await screen.findByRole("button", { name: "配置本机 Codex" }),
      );
      await user.click(await screen.findByText("查看完整指令"));
      const prompt = (
        await screen.findByRole<HTMLTextAreaElement>("textbox", {
          name: "Codex 接入提示词",
        })
      ).value;
      expect(prompt).toContain("installer.whl#sha256=test");
      expect(prompt).toContain("OCTOP_CODEX_PANEL_SYNC=1");
      expect(prompt).not.toContain("OCTOP_CODEX_EXTRACTION=octop");
      expect(api.setCodexModel).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

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
    for (const [name, marker] of [
      ["macOS / Linux", "read -rs"],
      ["Windows", "Read-Host"],
      ["交给 AI", "Token"],
      ["手动配置", "<TOKEN>"],
    ]) {
      await user.click(screen.getByRole("tab", { name }));
      const panel = screen.getByRole("tabpanel", { name });
      const command =
        within(panel).getByRole<HTMLTextAreaElement>("textbox").value;
      expect(command).toContain(marker);
      expect(command).not.toContain("omcp_live_plaintext_value");
      await user.click(within(panel).getByRole("button", { name: "复制命令" }));
      expect(copyMock).toHaveBeenLastCalledWith(command);
    }
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
      clientConfig("https://memory.example/mcp/"),
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

      await user.click(screen.getByText("查看完整指令"));
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
        expect(prompt).toContain("OCTOP_CODEX_PANEL_SYNC=1");
        expect(prompt).toContain("/api/memory-mcp/codex-review");
      } else {
        expect(prompt).not.toContain("memory_propose");
        expect(
          screen.queryByRole("combobox", { name: "记忆提取模型" }),
        ).toBeNull();
      }
    },
  );

  it("copies setup without needing or rotating the token", async () => {
    const user = userEvent.setup();
    render(<McpAccess />);
    await user.click(await screen.findByRole("button", { name: "接入配置" }));
    expect(copyMock).toHaveBeenCalledWith(clientConfig());
    expect(api.rotate).not.toHaveBeenCalled();
  });

  it("rotates only after confirmation and shows the new token once", async () => {
    api.list.mockResolvedValue([{ ...activeToken, space_id: "work" }]);
    api.rotate.mockResolvedValue({
      token: activeToken,
      plaintext: "omcp_rotated_secret",
    });
    const user = userEvent.setup();
    render(<McpAccess />);
    await user.click(await screen.findByRole("button", { name: "轮换 Token" }));
    expect(api.rotate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认轮换" }));
    expect(
      await screen.findByDisplayValue("omcp_rotated_secret"),
    ).toBeVisible();
    expect(api.rotate).toHaveBeenCalledWith("tok_1", "work");
    expect(copyMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /关\s*闭/ }));
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
    expect(screen.queryByDisplayValue("omcp_rotated_secret")).toBeNull();
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
