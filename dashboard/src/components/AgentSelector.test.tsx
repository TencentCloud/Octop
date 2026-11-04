import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { OctopAgent } from "../context/AgentContext";

const state = {
  agents: [] as OctopAgent[],
  activeAgentId: "writer" as string | null,
  loading: false,
};

const setActiveAgent = vi.fn((id: string | null) => {
  state.activeAgentId = id;
});

vi.mock("../context/AgentContext", () => ({
  useAgent: () => ({
    get agents() {
      return state.agents;
    },
    get activeAgentId() {
      return state.activeAgentId;
    },
    get loading() {
      return state.loading;
    },
    setActiveAgent,
  }),
}));

import AgentSelector from "./AgentSelector";

function fakeAgent(
  partial: Pick<OctopAgent, "agent_id" | "name"> & Partial<OctopAgent>,
): OctopAgent {
  return {
    id: 1,
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    state: "running",
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: "#2563eb",
    config: {},
    is_owner: true,
    kind: "expert",
    ...partial,
  };
}

const writer = fakeAgent({ agent_id: "writer", name: "写手" });
const crew = fakeAgent({
  agent_id: "crew",
  name: "调研团",
  kind: "team",
});
const remoteWriter = fakeAgent({
  agent_id: "bridge:c1:writer",
  name: "对端写手",
  bridge: true,
  bridge_connection_id: "c1",
  bridge_connection_name: "云端",
});
const remoteCrew = fakeAgent({
  agent_id: "bridge:c1:crew",
  name: "对端调研团",
  kind: "team",
  bridge: true,
  bridge_connection_id: "c1",
  bridge_connection_name: "云端",
});

describe("AgentSelector groups", () => {
  beforeEach(() => {
    setActiveAgent.mockClear();
    state.agents = [writer, crew];
    state.activeAgentId = "writer";
    state.loading = false;
  });

  it("hides teams unless showTeams is on", () => {
    const { rerender } = render(<AgentSelector />);
    const chips = () => within(screen.getByTestId("agent-selector-chips"));
    expect(chips().getByText("写手")).toBeInTheDocument();
    expect(chips().queryByText("调研团")).not.toBeInTheDocument();
    expect(screen.getByText("专家")).toBeInTheDocument();
    expect(chips().queryByText("团队")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "更多" }),
    ).not.toBeInTheDocument();
    expect(setActiveAgent).not.toHaveBeenCalled();

    rerender(<AgentSelector showTeams />);
    expect(chips().getByText("写手")).toBeInTheDocument();
    expect(chips().getByText("调研团")).toBeInTheDocument();
    expect(chips().getByText("专家")).toBeInTheDocument();
    expect(chips().getByText("团队")).toBeInTheDocument();
    expect(screen.queryByText("此页可管理专家和团队")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "更多" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("keeps groups in one chip row, including remotes", () => {
    state.agents = [writer, crew, remoteWriter, remoteCrew];
    render(<AgentSelector showTeams />);
    const chips = within(screen.getByTestId("agent-selector-chips"));
    expect(chips.getByText("专家")).toBeInTheDocument();
    expect(chips.getByText("团队")).toBeInTheDocument();
    expect(chips.getByText("云端·专家")).toBeInTheDocument();
    expect(chips.getByText("云端·团队")).toBeInTheDocument();
    expect(chips.getByText("对端写手")).toBeInTheDocument();
    expect(chips.getByText("对端调研团")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "更多" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("keeps a hidden team selection and asks the user to pick an expert", () => {
    state.activeAgentId = "crew";
    render(<AgentSelector />);
    expect(setActiveAgent).not.toHaveBeenCalled();
    expect(screen.queryByText("调研团")).not.toBeInTheDocument();
    expect(screen.getByText("专家")).toBeInTheDocument();
    expect(
      screen.getByText("当前是团队「调研团」，此页请选择专家"),
    ).toBeInTheDocument();
  });
});
