import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, vi } from "vitest";
import type { OctopAgent } from "../../../context/AgentContext";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";
import SessionList from "./SessionList";

function agent(
  partial: Pick<OctopAgent, "agent_id" | "name"> &
    Partial<Pick<OctopAgent, "kind" | "bridge">>,
): OctopAgent {
  return {
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
    color: null,
    config: {},
    ...partial,
  };
}

const agents = [
  agent({ agent_id: "local-expert", name: "本地专家" }),
  agent({
    agent_id: "bridge:c1:expert",
    name: "云端专家",
    bridge: true,
  }),
  agent({ agent_id: "local-team", name: "本地团队", kind: "team" }),
  agent({
    agent_id: "bridge:c1:team",
    name: "云端团队",
    kind: "team",
    bridge: true,
  }),
];

function renderList() {
  render(
    <MemoryRouter>
      <SessionList
        agents={agents}
        sessions={[]}
        activeId={null}
        activeAgentId="local-expert"
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => undefined}
        onFetchAllSessions={() => undefined}
        onSelect={() => undefined}
        onAgentSelect={() => undefined}
        onNewChat={() => undefined}
        onDelete={() => undefined}
        onRename={() => undefined}
        onPin={() => undefined}
        onFork={() => undefined}
      />
    </MemoryRouter>,
  );
}

describe("MinimalAgentSessionNav nav scopes", () => {
  beforeEach(() => {
    vi.spyOn(octopThreadsApi, "list").mockResolvedValue([]);
  });

  it("filters the same expert, team, and cloud tabs", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MinimalAgentSessionNav
          agents={agents}
          activeId={null}
          activeAgentId="local-expert"
          activeSessions={[]}
          onSelect={() => undefined}
          onAgentSelect={() => undefined}
          onNewChat={() => undefined}
          onDeleteActive={() => undefined}
          onRenameActive={() => undefined}
          onPinActive={() => undefined}
          onFork={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("本地专家")).toBeInTheDocument();
    expect(screen.getByText("云端专家")).toBeInTheDocument();
    expect(screen.queryByText("本地团队")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "云端" }));
    expect(screen.getByText("云端专家")).toBeInTheDocument();
    expect(screen.getByText("云端团队")).toBeInTheDocument();
    expect(screen.queryByText("本地专家")).not.toBeInTheDocument();
    expect(screen.queryByText("本地团队")).not.toBeInTheDocument();
  });
});

function LocationProbe() {
  const location = useLocation();
  return (
    <div>
      {location.pathname}
      {location.search}
    </div>
  );
}

describe("SessionList nav scopes", () => {
  it("filters experts, teams, and cloud under the search box", async () => {
    const user = userEvent.setup();
    renderList();

    expect(screen.getByRole("tab", { name: "专家" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("本地专家")).toBeInTheDocument();
    expect(screen.getByText("云端专家")).toBeInTheDocument();
    expect(screen.queryByText("本地团队")).not.toBeInTheDocument();
    expect(screen.queryByText("云端团队")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "团队" }));
    expect(screen.getByText("本地团队")).toBeInTheDocument();
    expect(screen.getByText("云端团队")).toBeInTheDocument();
    expect(screen.queryByText("本地专家")).not.toBeInTheDocument();
    expect(screen.queryByText("云端专家")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "云端" }));
    expect(screen.getByText("云端专家")).toBeInTheDocument();
    expect(screen.getByText("云端团队")).toBeInTheDocument();
    expect(screen.queryByText("本地专家")).not.toBeInTheDocument();
    expect(screen.queryByText("本地团队")).not.toBeInTheDocument();
  });

  it("links an empty team or cloud tab to the create page", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route
            path="/chat"
            element={
              <SessionList
                agents={[agent({ agent_id: "local-expert", name: "本地专家" })]}
                sessions={[]}
                activeId={null}
                activeAgentId="local-expert"
                hasMore={false}
                loadingMore={false}
                onLoadMore={() => undefined}
                onFetchAllSessions={() => undefined}
                onSelect={() => undefined}
                onAgentSelect={() => undefined}
                onNewChat={() => undefined}
                onDelete={() => undefined}
                onRename={() => undefined}
                onPin={() => undefined}
                onFork={() => undefined}
              />
            }
          />
          <Route path="/experts" element={<LocationProbe />} />
          <Route path="/bridge" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("tab", { name: "团队" }));
    await user.click(screen.getByRole("button", { name: "创建第一个团队" }));
    expect(screen.getByText("/experts?tab=teams")).toBeInTheDocument();
  });
});
