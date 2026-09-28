import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SessionList from "./SessionList";
import type { Session } from "../hooks/useSessions";
import type { InboxAgentRow, InboxByAgent } from "../hooks/useSessionInbox";
import type { OctopAgent } from "../../../context/AgentContext";
import {
  HIDDEN_SHARED_EXPERTS_STORAGE_KEY,
  hiddenExpertsStorageKey,
} from "../utils/hiddenExpertsPrefs";

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1, username: "tester" }),
}));

/** i18n is auto-mocked in this suite: bare keys resolve to the key itself. */
const T = {
  pinned: "chat.sectionPinned",
  active: "chat.sectionActive",
  unused: "chat.sectionUnused",
  projectBadge: "chat.projectSessionBadge",
  teamBadge: "chat.teamBadge",
  hide: "chat.expertHide",
  refresh: "common.refresh",
  search: "搜索会话",
};

function agent(
  overrides: Partial<OctopAgent> & {
    agent_id: string;
    name: string;
    id: number;
  },
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
    ...overrides,
  };
}

function session(overrides: Partial<Session> = {}): Session {
  return {
    id: "thr_1",
    name: "Session 1",
    threadId: "thr_1",
    updatedAt: "2026-01-02T00:00:00.000Z",
    channelType: "dashboard",
    hasActivity: true,
    agentId: "agent-a",
    ...overrides,
  };
}

function inbox(
  rows: Record<string, Partial<InboxAgentRow> & { agentId?: string }>,
): InboxByAgent {
  const out: InboxByAgent = {};
  for (const [agentId, row] of Object.entries(rows)) {
    out[agentId] = {
      agentId,
      sessionCount: row.sessionCount ?? 1,
      hasActivity: row.hasActivity ?? true,
      lastActive: row.lastActive ?? 0,
      pinned: row.pinned ?? [],
    };
  }
  return out;
}

/** Agent ids sort desc, so [a, b, c] is the render order. */
const AGENTS = [
  agent({ agent_id: "agent-a", name: "Alpha", id: 3 }),
  agent({ agent_id: "agent-b", name: "Bravo", id: 2, kind: "team" }),
  agent({ agent_id: "agent-c", name: "Charlie", id: 1 }),
];

type Props = React.ComponentProps<typeof SessionList>;

function renderList(overrides: Partial<Props> = {}) {
  const props: Props = {
    agents: AGENTS,
    sessions: [],
    activeId: null,
    activeAgentId: "agent-a",
    hasMore: false,
    loadingMore: false,
    inboxByAgent: inbox({
      "agent-a": { hasActivity: true, sessionCount: 1 },
      "agent-b": { hasActivity: false, sessionCount: 3 },
      // agent-c has no inbox row at all (zero-session agent).
    }),
    pinnedSessions: [],
    onLoadMore: vi.fn(),
    onFetchAllSessions: vi.fn(),
    onRefreshInbox: vi.fn(),
    onSelect: vi.fn(),
    onAgentSelect: vi.fn(),
    onNewChat: vi.fn(),
    onDelete: vi.fn(),
    onRename: vi.fn(),
    onPin: vi.fn(),
    onFork: vi.fn(),
    ...overrides,
  };
  const view = render(
    <MemoryRouter>
      <SessionList {...props} />
    </MemoryRouter>,
  );
  return { ...view, props };
}

const unusedHeader = (count: number) =>
  screen.getByRole("button", { name: `${T.unused} (${count})` });

describe("SessionList 三段式分组", () => {
  beforeEach(() => {
    localStorage.removeItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(hiddenExpertsStorageKey(1));
  });

  it("AC-S0-4/AC-S0-5/S-3：三段计数，has_activity=false 与零会话 agent 都落未使用段", () => {
    renderList();

    // 💬 会话：唯一 has_activity=true 的 agent。
    expect(screen.getByText(`${T.active} (1)`)).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();

    // 📦 未使用 = agents − 会话段 = agent-b（有 thread 行但 has_activity=false）+ agent-c（零会话）。
    expect(screen.getByText(`${T.unused} (2)`)).toBeInTheDocument();
    // 默认折叠：行不渲染，aria-expanded=false。
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Bravo")).not.toBeInTheDocument();
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();

    // 空置顶段整段不渲染。
    expect(
      screen.queryByText(new RegExp(`^${T.pinned}`)),
    ).not.toBeInTheDocument();
  });

  it("AC-S0-4/S-2：📦 默认折叠、可手动展开，搜索强制展开且清空后复原折叠态", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(unusedHeader(2));
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    expect(screen.getByText("Charlie")).toBeInTheDocument();

    // 再点一次回到折叠。
    await user.click(unusedHeader(2));
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "false");

    // 搜索强制展开（渲染期判定，不写回 state）。
    const search = screen.getByLabelText(T.search);
    await user.type(search, "bravo");
    expect(unusedHeader(1)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    // S-2：三段都按搜索词过滤 → 不匹配的 agent 行被过滤掉。
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();

    await user.clear(search);
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "false");
  });

  it("S-1：置顶段与段归属互不影响（置顶+无活动的会话仍在 📌，其 agent 仍在 📦）", async () => {
    const user = userEvent.setup();
    renderList({
      pinnedSessions: [
        session({
          id: "thr_pin",
          name: "Pinned no activity",
          agentId: "agent-b",
          hasActivity: false,
        }),
      ],
    });

    expect(screen.getByText(`${T.pinned} (1)`)).toBeInTheDocument();
    expect(screen.getByText("Pinned no activity")).toBeInTheDocument();
    // 该 agent 仍按 has_activity 落未使用段。
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "false");
    await user.click(unusedHeader(2));
    expect(screen.getByText("Bravo")).toBeInTheDocument();
  });

  it("S-2：搜索过滤 📌置顶段", async () => {
    const user = userEvent.setup();
    renderList({
      pinnedSessions: [
        session({ id: "thr_p1", name: "Alpha pinned", agentId: "agent-a" }),
        session({ id: "thr_p2", name: "Beta pinned", agentId: "agent-a" }),
      ],
    });

    expect(screen.getByText(`${T.pinned} (2)`)).toBeInTheDocument();
    await user.type(screen.getByLabelText(T.search), "beta");
    expect(screen.getByText("Beta pinned")).toBeInTheDocument();
    expect(screen.queryByText("Alpha pinned")).not.toBeInTheDocument();
    expect(screen.getByText(`${T.pinned} (1)`)).toBeInTheDocument();
  });

  it("S-6：隐藏专家的会话从 📌置顶段一并剔除", () => {
    localStorage.setItem(
      hiddenExpertsStorageKey(1),
      JSON.stringify(["agent-b"]),
    );
    renderList({
      inboxByAgent: inbox({
        "agent-a": { hasActivity: true, sessionCount: 1 },
        "agent-b": { hasActivity: true, sessionCount: 1 },
      }),
      pinnedSessions: [
        session({
          id: "thr_pin",
          name: "Bravo pinned",
          agentId: "agent-b",
        }),
      ],
    });

    expect(screen.queryByText("Bravo pinned")).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(`^${T.pinned}`)),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Bravo")).not.toBeInTheDocument();
  });

  it("S-8：全空态强制展开未使用段，侧栏不空白", () => {
    renderList({
      inboxByAgent: {},
      pinnedSessions: [],
      sessions: [],
    });

    expect(screen.getByText(`${T.unused} (3)`)).toBeInTheDocument();
    expect(unusedHeader(3)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("S-9：active agent 落未使用段时不得被折叠（负向：仍可见且会话行可达）", () => {
    renderList({
      activeAgentId: "agent-b",
      sessions: [session({ id: "thr_b1", name: "Bravo session" })],
      inboxByAgent: inbox({
        "agent-a": { hasActivity: true, sessionCount: 1 },
        "agent-b": { hasActivity: false, sessionCount: 1 },
      }),
    });

    expect(screen.getByText(`${T.unused} (2)`)).toBeInTheDocument();
    expect(unusedHeader(2)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    // 该 agent 的会话行可达（未被折叠进不可见状态）。
    expect(screen.getByText("Bravo session")).toBeInTheDocument();
  });

  it("S-4/AC-S0-6：agent 行渲染群聊标签（复用 TeamChatBadge），与会话行项目标签分置且顺序固定", () => {
    renderList({
      agents: [
        agent({ agent_id: "agent-a", name: "Alpha", id: 3, kind: "team" }),
        agent({ agent_id: "agent-b", name: "Bravo", id: 2 }),
        agent({ agent_id: "agent-c", name: "Charlie", id: 1 }),
      ],
      sessions: [
        session({
          id: "thr_proj",
          name: "Project session",
          projectId: "prj_1",
          projectName: "Apollo",
        }),
      ],
    });

    const team = screen.getByLabelText(T.teamBadge);
    const project = screen.getByLabelText(T.projectBadge);
    expect(team).toBeInTheDocument();
    expect(project).toBeInTheDocument();
    // 群聊 → 项目会话：agent 行的群聊标签在会话行项目标签之前。
    expect(
      team.compareDocumentPosition(project) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("S-10：手动刷新入口存在且只在用户点击时取数（搜索不触发）", async () => {
    const user = userEvent.setup();
    const { props } = renderList();

    const refresh = screen.getByLabelText(T.refresh);
    expect(refresh).toBeInTheDocument();

    await user.type(screen.getByLabelText(T.search), "alpha");
    expect(props.onRefreshInbox).not.toHaveBeenCalled();

    await user.click(refresh);
    expect(props.onRefreshInbox).toHaveBeenCalledTimes(1);
  });

  it("AC-S0-4：每个 agent 行显示 inbox 的 session_count（▸ n）", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(unusedHeader(2));
    expect(screen.getByText(/▸ 3/)).toBeInTheDocument();
  });
});

describe("SessionList 项目会话（T2.6）", () => {
  it("正向：projectId 非空的会话渲染「项目会话」标签并按 projectName 分组", () => {
    renderList({
      sessions: [
        session({
          id: "thr_proj",
          name: "Apollo chat",
          projectId: "prj_1",
          projectName: "Apollo",
        }),
        session({ id: "thr_plain", name: "Manual chat", projectId: null }),
      ],
    });

    expect(screen.getByText("Apollo (1)")).toBeInTheDocument();
    expect(screen.getAllByText(T.projectBadge)).toHaveLength(1);
    expect(screen.getByText("Apollo chat")).toBeInTheDocument();
    expect(screen.getByText("Manual chat")).toBeInTheDocument();
  });

  it("负向：projectId 为空的会话不得带项目标签，也不渲染项目分组头", () => {
    renderList({
      sessions: [session({ id: "thr_plain", name: "Manual chat" })],
    });

    expect(screen.queryByText(T.projectBadge)).not.toBeInTheDocument();
    expect(screen.queryByText(/Apollo/)).not.toBeInTheDocument();
  });

  it("置顶段按 projectName 渲染项目分组头", () => {
    renderList({
      pinnedSessions: [
        session({
          id: "thr_p1",
          name: "Pinned Apollo",
          agentId: "agent-a",
          projectId: "prj_1",
          projectName: "Apollo",
        }),
        session({
          id: "thr_p2",
          name: "Pinned manual",
          agentId: "agent-a",
        }),
      ],
    });

    expect(screen.getByText(`${T.pinned} (2)`)).toBeInTheDocument();
    expect(screen.getByText("Apollo (1)")).toBeInTheDocument();
    expect(screen.getAllByText(T.projectBadge)).toHaveLength(1);
  });
});
