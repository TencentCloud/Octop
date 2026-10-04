import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AgentSettingsPanel from "./AgentSettingsPanel";

vi.mock("../context/AgentContext", () => ({
  useAgent: () => ({
    activeAgentId: "team-a",
    activeAgent: { agent_id: "team-a", name: "Team A", kind: "team" },
  }),
}));
vi.mock("../pages/Agent/Memory/MemoryPanel", () => ({
  default: ({ agentId }: { agentId: string }) => <span>Memory {agentId}</span>,
}));
vi.mock("../pages/Agent/Channels/ChannelsPanel", () => ({
  default: ({ agentId }: { agentId: string }) => (
    <span>Channels {agentId}</span>
  ),
}));
vi.mock("../pages/Agent/Tools/ToolsTabs", () => ({
  default: () => <span>Expert tools</span>,
}));
vi.mock("../pages/Agent/Personalization/components/MBTISelector", () => ({
  default: () => <span>Expert personality</span>,
}));
vi.mock("../pages/Agent/Personalization/components/AgentPluginsPanel", () => ({
  default: () => <span>Expert plugins</span>,
}));
vi.mock("../pages/Experts/components/SubagentManager", () => ({
  default: () => <span>Expert subagents</span>,
}));
vi.mock("../pages/Agent/Config", () => ({
  default: () => <span>Expert config</span>,
}));

describe("Agent settings scope", () => {
  it.each(["memory", "channels"])("retains team %s", (panel) => {
    render(<AgentSettingsPanel panel={panel} />);
    expect(screen.getByText(/team-a/)).toBeInTheDocument();
  });
  it.each(["tools", "plugins", "subagents", "config", "personality"])(
    "does not mount expert-only %s for a team",
    (panel) => {
      render(<AgentSettingsPanel panel={panel} />);
      expect(
        screen.getByText("agentSelector.teamNeedsExpert"),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Expert /)).not.toBeInTheDocument();
    },
  );
});
