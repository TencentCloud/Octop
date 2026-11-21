import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  default: {
    getStrongMemory: vi.fn(),
    putStrongMemory: vi.fn(),
    getUserProfile: vi.fn(),
    putUserProfile: vi.fn(),
    getManualMemoryReview: vi.fn(),
    reviewManualMemory: vi.fn(),
  },
}));
vi.mock("../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

import memoryApi from "../../../api/modules/memoryDashboard";
import { message } from "../../../utils/antdMessage";
import StrongMemory from "./StrongMemory";

const api = vi.mocked(memoryApi);

beforeEach(() => {
  vi.resetAllMocks();
  const empty = {
    status: "complete",
    conflicts: 0,
    duplicates: 0,
    checked: 0,
    remaining: 0,
    candidate_ids: [],
  };
  api.getManualMemoryReview.mockResolvedValue(empty);
  api.reviewManualMemory.mockResolvedValue(empty);
});

describe("Strong memory", () => {
  it("does not overwrite a new audit with delayed initial status", async () => {
    let resolveStatus!: (
      value: Awaited<ReturnType<typeof memoryApi.getManualMemoryReview>>,
    ) => void;
    api.getManualMemoryReview.mockReturnValue(
      new Promise((resolve) => {
        resolveStatus = resolve;
      }),
    );
    api.getUserProfile.mockResolvedValue({ content: "", exists: false });
    api.putUserProfile.mockResolvedValue({ content: "新档案", exists: true });
    api.reviewManualMemory.mockResolvedValue({
      status: "complete",
      conflicts: 1,
      duplicates: 0,
      checked: 1,
      remaining: 0,
      candidate_ids: ["c1"],
    });
    const user = userEvent.setup();
    render(<StrongMemory agentId="a1" document="user" />);
    const editor = await screen.findByRole("textbox", {
      name: "用户档案内容（USER.md）",
    });
    await user.type(editor, "新档案");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    expect(await screen.findByText(/发现 1 条冲突/)).toBeInTheDocument();
    await act(async () =>
      resolveStatus({
        status: "stale",
        conflicts: 0,
        duplicates: 0,
        checked: 0,
        remaining: 0,
        candidate_ids: [],
      }),
    );
    expect(screen.getByText(/发现 1 条冲突/)).toBeInTheDocument();
    expect(
      screen.queryByText("手动文档已变化，请重新核对。"),
    ).not.toBeInTheDocument();
  });

  it("edits USER.md separately and shows conflicts moved to candidates", async () => {
    api.getUserProfile.mockResolvedValue({
      content: "姓名：小王",
      exists: true,
    });
    api.putUserProfile.mockResolvedValue({
      content: "姓名：小李",
      exists: true,
    });
    api.reviewManualMemory.mockResolvedValue({
      status: "complete",
      conflicts: 1,
      duplicates: 2,
      checked: 3,
      remaining: 0,
      candidate_ids: ["c-1"],
    });
    const onReview = vi.fn();
    const user = userEvent.setup();
    render(
      <StrongMemory
        agentId="agent-a"
        document="user"
        onReviewCandidates={onReview}
      />,
    );
    const editor = await screen.findByRole("textbox", {
      name: "用户档案内容（USER.md）",
    });
    expect(editor).toHaveValue("姓名：小王");
    expect(
      screen.getByText(/USER.md 由你手动维护，Agent 只读/),
    ).toBeInTheDocument();
    await user.clear(editor);
    await user.type(editor, "姓名：小李");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(api.putUserProfile).toHaveBeenCalledWith("agent-a", "姓名：小李"),
    );
    expect(api.putStrongMemory).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/发现 1 条冲突，已转为候选待审核/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看候选" }));
    expect(onReview).toHaveBeenCalledOnce();
  });

  it("keeps a successful profile save when semantic review is unavailable", async () => {
    api.getUserProfile.mockResolvedValue({ content: "", exists: false });
    api.putUserProfile.mockResolvedValue({ content: "新档案", exists: true });
    api.reviewManualMemory.mockResolvedValue({
      status: "unavailable",
      conflicts: 0,
      duplicates: 0,
      checked: 0,
      remaining: 1,
      candidate_ids: [],
    });
    const user = userEvent.setup();
    render(<StrongMemory agentId="agent-a" document="user" />);
    const editor = await screen.findByRole("textbox", {
      name: "用户档案内容（USER.md）",
    });
    await user.type(editor, "新档案");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    expect(
      await screen.findByText(/语义检查不可用，尚未完成核对/),
    ).toBeInTheDocument();
    expect(editor).toHaveValue("新档案");
    expect(message.success).toHaveBeenCalledWith(
      expect.stringContaining("已保存"),
    );
  });

  it("does not leak a delayed MEMORY.md response into USER.md", async () => {
    let resolveOld!: (value: { content: string; exists: boolean }) => void;
    api.getStrongMemory.mockReturnValue(
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
    );
    api.getUserProfile.mockResolvedValue({ content: "用户档案", exists: true });
    const { rerender } = render(<StrongMemory agentId="agent-a" />);
    rerender(<StrongMemory agentId="agent-a" document="user" />);
    const editor = await screen.findByRole("textbox", {
      name: "用户档案内容（USER.md）",
    });
    await waitFor(() => expect(editor).toHaveValue("用户档案"));
    resolveOld({ content: "旧强记忆", exists: true });
    await waitFor(() => expect(editor).toHaveValue("用户档案"));
  });
  it("loads the full manual document and saves it to the selected agent", async () => {
    const original = "# 手工约定\n\n每次都先给结论。\n";
    api.getStrongMemory.mockResolvedValue({ content: original, exists: true });
    api.putStrongMemory.mockResolvedValue({
      content: "新的手工约定",
      exists: true,
    });
    const user = userEvent.setup();
    render(<StrongMemory agentId="agent-a" />);
    const editor = await screen.findByRole("textbox", { name: "强记忆内容" });
    expect(editor).toHaveValue(original);
    expect(
      screen.getByText(/每个会话开始时加载一次强记忆/),
    ).toBeInTheDocument();
    expect(screen.getByText(/修改后对新会话生效/)).toBeInTheDocument();
    await user.clear(editor);
    await user.type(editor, "新的手工约定");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(api.putStrongMemory).toHaveBeenCalledWith(
        "agent-a",
        "新的手工约定",
      ),
    );
    await waitFor(() =>
      expect(message.success).toHaveBeenCalledWith(
        expect.stringContaining("新会话"),
      ),
    );
  });

  it("keeps saving disabled after a failed read", async () => {
    api.getStrongMemory.mockRejectedValue(new Error("offline"));
    render(<StrongMemory agentId="agent-a" />);
    expect(
      await screen.findByText("加载强记忆失败，请重试。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保\s*存/ })).toBeDisabled();
    expect(api.putStrongMemory).not.toHaveBeenCalled();
  });

  it("keeps the draft after a failed save and allows clearing the document", async () => {
    api.getStrongMemory.mockResolvedValue({
      content: "原有内容",
      exists: true,
    });
    api.putStrongMemory.mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    render(<StrongMemory agentId="agent-a" />);
    const editor = await screen.findByRole("textbox", { name: "强记忆内容" });
    await user.clear(editor);
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(api.putStrongMemory).toHaveBeenCalledWith("agent-a", ""),
    );
    expect(editor).toHaveValue("");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /保\s*存/ })).toBeEnabled(),
    );
  });

  it("ignores a previous agent's delayed response", async () => {
    let resolveOld!: (value: { content: string; exists: boolean }) => void;
    api.getStrongMemory.mockImplementation((id) =>
      id === "agent-a"
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve({ content: "B 的内容", exists: true }),
    );
    const { rerender } = render(<StrongMemory agentId="agent-a" />);
    rerender(<StrongMemory agentId="agent-b" />);
    const editor = await screen.findByRole("textbox", { name: "强记忆内容" });
    await waitFor(() => expect(editor).toHaveValue("B 的内容"));
    resolveOld({ content: "A 的旧内容", exists: true });
    await waitFor(() => expect(editor).toHaveValue("B 的内容"));
  });
});
