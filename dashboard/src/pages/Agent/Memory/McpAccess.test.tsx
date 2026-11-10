import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

vi.mock("../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
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
import { message } from "../../../utils/antdMessage";
import { copyText } from "../../../utils/copyText";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import McpAccess from "./McpAccess";

const api = vi.mocked(memoryMcpApi, true);
const copyMock = vi.mocked(copyText);

/** The MCP client config a row copies. */
function clientConfig(plaintext: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        "octop-memory": {
          type: "http",
          url: `${window.location.origin}/mcp/memory/`,
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
});

describe("<McpAccess />", () => {
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
      }),
    );
    expect(
      await screen.findByDisplayValue("omcp_live_plaintext_value"),
    ).toBeInTheDocument();
    expect(screen.getByText(/只显示这一次/)).toBeInTheDocument();
    // The list is refreshed after a successful create.
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
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
      name: /接入命令/,
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

    await user.click(screen.getByRole("button", { name: /接入命令/ }));
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
    expect(screen.getByRole("button", { name: /接入命令/ })).toBeDisabled();
  });
});
