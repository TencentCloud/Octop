import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryMcp", () => ({
  memoryMcpApi: {
    list: vi.fn(),
    create: vi.fn(),
    revoke: vi.fn(),
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

import {
  memoryMcpApi,
  type MemoryMcpToken,
} from "../../../api/modules/memoryMcp";
import McpAccess from "./McpAccess";

const api = vi.mocked(memoryMcpApi, true);

const activeToken: MemoryMcpToken = {
  token_id: "tok_1",
  name: "codex@macbook",
  expert_ids: null,
  token_hint: "omcp_…abcd",
  created_at: "2026-11-09T08:00:00Z",
  last_used_at: null,
  revoked_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue([activeToken]);
});

describe("<McpAccess />", () => {
  it("renders the token hint, unscoped experts and active status", async () => {
    render(<McpAccess />);

    expect(await screen.findByText("codex@macbook")).toBeInTheDocument();
    expect(screen.getByText("omcp_…abcd")).toBeInTheDocument();
    expect(screen.getByText("不限专家")).toBeInTheDocument();
    expect(screen.getByText("有效")).toBeInTheDocument();
    expect(screen.getByText("从未使用")).toBeInTheDocument();
    expect(api.list).toHaveBeenCalledTimes(1);
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
    await user.click(screen.getByRole("button", { name: /^创\s*建$/ }));

    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith({
        name: "claude@laptop",
        expert_ids: null,
      }),
    );
    expect(
      await screen.findByDisplayValue("omcp_live_plaintext_value"),
    ).toBeInTheDocument();
    expect(screen.getByText(/只显示这一次/)).toBeInTheDocument();
    // The list is refreshed after a successful create.
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
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

  it("shows the revoked state and disables revoke for revoked tokens", async () => {
    api.list.mockResolvedValue([
      { ...activeToken, revoked_at: "2026-11-09T09:00:00Z" },
    ]);
    render(<McpAccess />);

    expect(await screen.findByText("已撤销")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /撤\s*销/ })).toBeDisabled();
  });
});
