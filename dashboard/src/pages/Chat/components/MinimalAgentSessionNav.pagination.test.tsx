import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  octopThreadsApi,
  type OctopThread,
} from "../../../api/modules/octopThreads";
import type { OctopAgent } from "../../../context/AgentContext";
import { emitSessionEvent } from "../hooks/chatStore";
import type { Session } from "../hooks/useSessions";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";

function agent(
  partial: Pick<OctopAgent, "id" | "agent_id" | "name">,
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
  agent({ id: 2, agent_id: "shared", name: "共享专家" }),
  agent({ id: 1, agent_id: "other", name: "其他专家" }),
];

function threads(agentId: string, count: number): OctopThread[] {
  return Array.from({ length: count }, (_, index) => ({
    thread_id: `${agentId}-${index + 1}`,
    title: `${agentId} 会话 ${index + 1}`,
    channel_type: "dashboard",
    session_key: `${agentId}:dash`,
    last_active: 1000 - index,
    created_at: 1000 - index,
    has_messages: true,
  }));
}

function pageFor(agentId: string): OctopThread[] {
  return threads(agentId, agentId === "other" ? 10 : 23);
}

function asSession(row: OctopThread): Session {
  return {
    id: row.thread_id,
    threadId: row.thread_id,
    name: row.title ?? "",
    updatedAt: new Date(row.last_active * 1000).toISOString(),
    channelType: "dashboard",
  };
}

function renderNav(
  extra?: Partial<ComponentProps<typeof MinimalAgentSessionNav>>,
) {
  const onSelect = extra?.onSelect ?? vi.fn();
  const view = render(
    <MemoryRouter>
      <MinimalAgentSessionNav
        agents={agents}
        activeId={null}
        activeAgentId={null}
        activeSessions={[]}
        onSelect={onSelect}
        onAgentSelect={vi.fn()}
        onNewChat={vi.fn()}
        onDeleteActive={vi.fn()}
        onRenameActive={vi.fn()}
        onPinActive={vi.fn()}
        onFork={vi.fn()}
        {...extra}
      />
    </MemoryRouter>,
  );
  return { ...view, onSelect };
}

describe("minimal expert conversation pagination", () => {
  const list = vi.spyOn(octopThreadsApi, "list");

  beforeEach(() => {
    localStorage.clear();
    list.mockReset();
    list.mockImplementation(async (id: string, limit = 50) =>
      pageFor(id).slice(0, limit),
    );
  });

  it("loads older sessions per expert and keeps them when the live page is shorter", async () => {
    const { onSelect, rerender } = renderNav();
    await screen.findByText("shared 会话 10");
    expect(screen.queryByText("shared 会话 11")).toBeNull();

    const shared = screen.getByText("共享专家").closest("section")!;
    const other = screen.getByText("其他专家").closest("section")!;
    expect(within(other).queryByText("展开更多")).toBeNull();

    fireEvent.click(within(shared).getByText("展开更多"));
    await within(shared).findByText("shared 会话 20");
    expect(within(other).queryByText("other 会话 11")).toBeNull();

    fireEvent.click(within(shared).getByText("shared 会话 11"));
    expect(onSelect).toHaveBeenCalledWith("shared-11", "shared");

    rerender(
      <MemoryRouter>
        <MinimalAgentSessionNav
          agents={agents}
          activeId="shared-11"
          activeAgentId="shared"
          activeSessions={pageFor("shared").slice(0, 10).map(asSession)}
          onSelect={onSelect}
          onAgentSelect={vi.fn()}
          onNewChat={vi.fn()}
          onDeleteActive={vi.fn()}
          onRenameActive={vi.fn()}
          onPinActive={vi.fn()}
          onFork={vi.fn()}
        />
      </MemoryRouter>,
    );
    const sharedAfter = screen.getByText("共享专家").closest("section")!;
    expect(within(sharedAfter).getByText("shared 会话 11")).toBeTruthy();

    fireEvent.click(within(sharedAfter).getByText("展开更多"));
    await within(sharedAfter).findByText("shared 会话 23");
    expect(within(sharedAfter).queryByText("展开更多")).toBeNull();
  });

  it("keeps the expand button available after a request fails", async () => {
    renderNav();
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
    let resolveOlder: (value: OctopThread[]) => void = () => {};
    renderNav();
    await screen.findByText("shared 会话 10");
    const shared = screen.getByText("共享专家").closest("section")!;
    list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOlder = resolve;
        }),
    );
    fireEvent.click(within(shared).getByText("展开更多"));
    act(() => {
      emitSessionEvent({
        kind: "sessionsChanged",
        sessionId: "shared-1",
        agentId: "shared",
      });
    });
    await within(shared).findByText("shared 会话 20");
    expect(list).toHaveBeenLastCalledWith("shared", 21);
    await act(async () => {
      resolveOlder(pageFor("shared").slice(0, 21));
    });
    expect(within(shared).getByText("shared 会话 20")).toBeTruthy();
    expect(within(shared).queryByText("shared 会话 21")).toBeNull();
  });

  it("hides expand while search is showing the session catalog", async () => {
    renderNav();
    await screen.findByText("shared 会话 10");
    expect(screen.getAllByText("展开更多")).toHaveLength(1);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "会话 23" },
    });
    await screen.findByText("shared 会话 23");
    expect(screen.queryByText("展开更多")).toBeNull();
  });
});
