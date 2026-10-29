import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";
import type { OctopAgent } from "../../../context/AgentContext";
import type { Session } from "../hooks/useSessions";
import { emitSessionEvent } from "../hooks/chatStore";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: { list },
  normalizeThreadArtifacts: () => [],
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) =>
      typeof fallback === "string" ? fallback : _key,
  }),
}));
vi.mock("antd", () => ({
  Dropdown: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../hooks/useSessionWorkIds", () => ({
  useSessionWorkIds: () => new Set<string>(),
}));
vi.mock("../../../utils/agentError", () => ({ isAgentChatReady: () => true }));
vi.mock("../../Experts/components/iconForName", () => ({
  ExpertIcon: () => null,
}));
vi.mock("./SharedExpertHint", () => ({ default: () => null }));
vi.mock("./RemoteExpertHint", () => ({ default: () => null }));
vi.mock("./TeamChatBadge", () => ({ default: () => null }));
vi.mock("./SessionWorkStatusIcon", () => ({ default: () => null }));

const agents = [
  { id: 2, agent_id: "shared", name: "共享专家", state: "running" },
  { id: 1, agent_id: "other", name: "其他专家", state: "running" },
] as OctopAgent[];
const rows = (agent: string) =>
  Array.from({ length: 23 }, (_, index) => ({
    thread_id: `${agent}-${index + 1}`,
    title: `${agent} 会话 ${index + 1}`,
    last_active: 1000 - index,
    has_messages: true,
  }));
const props = {
  agents,
  activeId: null,
  activeAgentId: null,
  activeSessions: [] as Session[],
  onSelect: vi.fn(),
  onAgentSelect: vi.fn(),
  onNewChat: vi.fn(),
  onDeleteActive: vi.fn(),
  onRenameActive: vi.fn(),
  onPinActive: vi.fn(),
  onFork: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  list.mockImplementation(async (id: string, limit: number) =>
    rows(id).slice(0, limit),
  );
});

describe("minimal expert conversation pagination", () => {
  it("loads older sessions independently and retains them when selecting one", async () => {
    const onSelect = vi.fn();
    const view = render(
      <MinimalAgentSessionNav {...props} onSelect={onSelect} />,
    );
    await screen.findByText("shared 会话 10");
    expect(screen.queryByText("shared 会话 11")).toBeNull();
    const shared = screen.getByText("共享专家").closest("section")!;
    const other = screen.getByText("其他专家").closest("section")!;
    fireEvent.click(within(shared).getByText("展开更多"));
    await within(shared).findByText("shared 会话 20");
    expect(within(other).queryByText("other 会话 11")).toBeNull();
    fireEvent.click(within(shared).getByText("shared 会话 11"));
    expect(onSelect).toHaveBeenCalledWith("shared-11", "shared");
    const activeSessions = rows("shared")
      .slice(0, 10)
      .map((row) => ({
        id: row.thread_id,
        threadId: row.thread_id,
        name: row.title,
        updatedAt: new Date(row.last_active * 1000).toISOString(),
        channelType: "dashboard",
      }));
    view.rerender(
      <MinimalAgentSessionNav
        {...props}
        onSelect={onSelect}
        activeAgentId="shared"
        activeId="shared-11"
        activeSessions={activeSessions}
      />,
    );
    expect(within(shared).getByText("shared 会话 11")).toBeTruthy();
    fireEvent.click(within(shared).getByText("展开更多"));
    await within(shared).findByText("shared 会话 23");
    expect(within(shared).queryByText("展开更多")).toBeNull();
  });

  it("keeps the expand button available after a request fails", async () => {
    render(<MinimalAgentSessionNav {...props} />);
    await screen.findByText("shared 会话 10");
    const shared = screen.getByText("共享专家").closest("section")!;
    list.mockRejectedValueOnce(new Error("network"));
    fireEvent.click(within(shared).getByText("展开更多"));
    await waitFor(() =>
      expect(within(shared).getByText("展开更多")).not.toBeDisabled(),
    );
    fireEvent.click(within(shared).getByText("展开更多"));
    await within(shared).findByText("shared 会话 11");
  });

  it("keeps the requested page size when a session event refreshes during expansion", async () => {
    let resolveOlder: (value: ReturnType<typeof rows>) => void = () => {};
    render(<MinimalAgentSessionNav {...props} />);
    await screen.findByText("shared 会话 10");
    const shared = screen.getByText("共享专家").closest("section")!;
    list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOlder = resolve;
        }),
    );
    fireEvent.click(within(shared).getByText("展开更多"));
    act(() => emitSessionEvent({ kind: "sessionsChanged", agentId: "shared" }));
    await within(shared).findByText("shared 会话 20");
    expect(list).toHaveBeenLastCalledWith("shared", 21);
    await act(async () => {
      resolveOlder(rows("shared").slice(0, 21));
    });
    expect(within(shared).getByText("shared 会话 20")).toBeTruthy();
  });
});
