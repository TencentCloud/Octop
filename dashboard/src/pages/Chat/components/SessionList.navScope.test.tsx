import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import type { OctopAgent } from "../../../context/AgentContext";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";
import SessionList from "./SessionList";
import { resetSessionStoreForTests, useSessions } from "../hooks/useSessions";

afterEach(() => vi.restoreAllMocks());

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
        onArchive={() => undefined}
        showArchived={false}
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
          onArchiveActive={() => undefined}
          showArchived={false}
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
                onArchive={() => undefined}
                showArchived={false}
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

describe("SessionList archive search pagination", () => {
  beforeEach(() => resetSessionStoreForTests());
  afterEach(() => resetSessionStoreForTests());

  it("keeps the search term and loads the eleventh archived session", async () => {
    const user = userEvent.setup();
    vi.spyOn(octopThreadsApi, "list").mockImplementation(
      async (_agentId, limit = 50, archived = false) =>
        Array.from({ length: 11 }, (_, index) => ({
          thread_id: `${archived ? "archive" : "current"}-${index}`,
          title:
            index === 10
              ? `needle ${archived ? "archived" : "current"}`
              : `Session ${index}`,
          last_active: 20 - index,
          session_key: "key",
          channel_type: "dashboard",
          archived,
        })).slice(0, limit),
    );

    function ActiveArchiveSearch() {
      const sessions = useSessions("local-expert");
      return (
        <>
          <button onClick={() => sessions.setShowArchived(true)}>
            Show archived
          </button>
          <SessionList
            agents={[
              agent({ agent_id: "local-expert", name: "needle expert" }),
            ]}
            sessions={sessions.sessions}
            activeId={null}
            activeAgentId="local-expert"
            hasMore={sessions.hasMore}
            loadingMore={sessions.loadingMore}
            onLoadMore={sessions.loadMoreSessions}
            onFetchAllSessions={sessions.fetchAllSessions}
            onSelect={vi.fn()}
            onAgentSelect={vi.fn()}
            onNewChat={vi.fn()}
            onDelete={vi.fn()}
            onRename={vi.fn()}
            onPin={vi.fn()}
            onArchive={vi.fn()}
            onFork={vi.fn()}
            showArchived={sessions.showArchived}
          />
        </>
      );
    }
    render(
      <MemoryRouter>
        <ActiveArchiveSearch />
      </MemoryRouter>,
    );
    await screen.findByText("Session 0");
    await user.type(
      screen.getByRole("searchbox", { name: "搜索会话" }),
      "needle",
    );
    await screen.findByText("needle current");
    await user.click(screen.getByRole("button", { name: "Show archived" }));

    expect(await screen.findByText("needle archived")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "搜索会话" })).toHaveValue(
      "needle",
    );
  });
});

describe.each(["classic", "minimal"] as const)(
  "%s cross-expert archive actions",
  (variant) => {
    it.each([false, true])(
      "routes archived=%s to the selected expert",
      async (showArchived) => {
        const user = userEvent.setup();
        const onArchive = vi.fn();
        vi.spyOn(octopThreadsApi, "list").mockImplementation(
          async (agentId, _limit, archived) =>
            agentId === "other-expert"
              ? [
                  {
                    thread_id: "other-thread",
                    title: "matching session",
                    session_key: "other-key",
                    channel_type: "dashboard",
                    last_active: 1,
                    archived: Boolean(archived),
                  },
                ]
              : [],
        );
        const patch = vi.spyOn(octopThreadsApi, "patch").mockResolvedValue({
          thread_id: "other-thread",
          title: "matching session",
        });
        const common = {
          agents: [
            agents[0],
            agent({ agent_id: "other-expert", name: "Other expert" }),
          ],
          activeId: null,
          activeAgentId: "local-expert",
          onSelect: vi.fn(),
          onAgentSelect: vi.fn(),
          onNewChat: vi.fn(),
          onFork: vi.fn(),
          showArchived,
        };
        render(
          <MemoryRouter>
            {variant === "classic" ? (
              <SessionList
                {...common}
                sessions={[]}
                hasMore={false}
                loadingMore={false}
                onLoadMore={vi.fn()}
                onFetchAllSessions={vi.fn()}
                onDelete={vi.fn()}
                onRename={vi.fn()}
                onPin={vi.fn()}
                onArchive={onArchive}
              />
            ) : (
              <MinimalAgentSessionNav
                {...common}
                activeSessions={[]}
                onDeleteActive={vi.fn()}
                onRenameActive={vi.fn()}
                onPinActive={vi.fn()}
                onArchiveActive={onArchive}
              />
            )}
          </MemoryRouter>,
        );

        await user.type(
          screen.getByRole("searchbox", { name: "搜索会话" }),
          "matching",
        );
        expect(await screen.findByText("matching session")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "More" }));
        await user.click(
          await screen.findByText(
            showArchived
              ? "chat.restoreConversation"
              : "chat.archiveConversation",
          ),
        );

        await waitFor(() =>
          expect(patch).toHaveBeenCalledWith("other-expert", "other-thread", {
            archived: !showArchived,
          }),
        );
        await waitFor(() =>
          expect(
            screen.queryByText("matching session"),
          ).not.toBeInTheDocument(),
        );
        expect(onArchive).not.toHaveBeenCalled();
      },
    );
  },
);
