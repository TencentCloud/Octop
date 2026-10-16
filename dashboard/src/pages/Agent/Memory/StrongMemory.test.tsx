import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  default: { getStrongMemory: vi.fn(), putStrongMemory: vi.fn() },
}));

import memoryApi from "../../../api/modules/memoryDashboard";
import StrongMemory from "./StrongMemory";

const api = vi.mocked(memoryApi);

beforeEach(() => vi.resetAllMocks());

describe("Strong memory", () => {
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
      screen.getByText(/每次聊天都会将这里的全部内容加入上下文/),
    ).toBeInTheDocument();
    await user.clear(editor);
    await user.type(editor, "新的手工约定");
    await user.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(api.putStrongMemory).toHaveBeenCalledWith(
        "agent-a",
        "新的手工约定",
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
