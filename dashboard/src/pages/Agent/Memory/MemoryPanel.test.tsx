import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import MemoryPanel from "./MemoryPanel";

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ agents: [{ agent_id: "expert-a", kind: "expert" }] }),
}));

vi.mock("../../../api/modules/memoryDashboard", () => ({
  default: {
    statsCounts: vi.fn().mockResolvedValue({ candidates_pending: 0 }),
  },
}));

vi.mock("./Overview", () => ({ default: () => null }));

vi.mock("./McpAccess", () => ({
  default: () => <div>终端凭据列表</div>,
}));

describe("MemoryPanel terminal access", () => {
  it("shows the active terminal access tab even without an expert", () => {
    render(
      <MemoryPanel
        agentId={null}
        mcpAccess={{ active: true, onChange: vi.fn() }}
      />,
    );

    expect(
      screen.getByRole("tab", { name: "共享记忆", selected: true }),
    ).toBeVisible();
    expect(screen.getByText("终端凭据列表")).toBeVisible();
  });

  it("requests terminal access when its tab is selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <MemoryPanel
        agentId="expert-a"
        mcpAccess={{ active: false, onChange }}
      />,
    );

    await user.click(screen.getByRole("tab", { name: "共享记忆" }));

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("keeps terminal access out of panels without the opt-in", () => {
    render(<MemoryPanel agentId="expert-a" />);

    expect(screen.getByRole("tab", { name: "概览" })).toBeVisible();
    expect(
      screen.queryByRole("tab", { name: "共享记忆" }),
    ).not.toBeInTheDocument();
  });
});
