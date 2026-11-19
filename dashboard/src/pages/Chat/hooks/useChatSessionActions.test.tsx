import { renderHook, act, fireEvent, screen } from "@testing-library/react";
import { Link, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import {
  octopThreadsApi,
  type OctopThread,
} from "../../../api/modules/octopThreads";
import { useChatSessionActions } from "./useChatSessionActions";
import {
  appendUserMessage,
  getSnapshot,
  removeSession,
  type ChatMessage,
} from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY } from "../constants";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../../api/modules/octopThreads", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/octopThreads")
  >();
  return {
    ...actual,
    octopThreadsApi: {
      ...actual.octopThreadsApi,
      rebind: vi.fn().mockResolvedValue({}),
      list: vi.fn().mockResolvedValue([]),
    },
  };
});

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

const THREAD = "thr_leaving";

function makeMessage(id: string): ChatMessage {
  return { id, role: "user", content: `message ${id}`, timestamp: Date.now() };
}

function renderActions(markInitialNavDone = vi.fn(), router = wrapper) {
  return renderHook(
    () =>
      useChatSessionActions({
        resolvedAgentId: "agent-a",
        activeThreadId: THREAD,
        sessions: [],
        isMobile: false,
        setActiveAgent: vi.fn(),
        setSidebarOpen: vi.fn(),
        setSelectedModel: vi.fn(),
        setHasBrowserTool: vi.fn(),
        deleteSession: vi.fn().mockResolvedValue(true),
        clearMessages: vi.fn(),
        resetNavForAgentSwitch: vi.fn(),
        markInitialNavDone,
      }),
    { wrapper: router },
  );
}

describe("New Chat", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("disables automatic history selection before navigating to the blank composer", () => {
    const markInitialNavDone = vi.fn(() => {
      expect(navigateMock).not.toHaveBeenCalled();
    });
    const { result } = renderActions(markInitialNavDone);

    act(() => result.current.handleNewChat());

    expect(markInitialNavDone).toHaveBeenCalledWith("agent-a");
    expect(navigateMock).toHaveBeenCalledWith("/chat/agent-a");
  });

  it.each(["handleNewChat", "handleNewChatWithAgent"] as const)(
    "ignores a late expert list after %s",
    async (action) => {
      let complete!: (rows: OctopThread[]) => void;
      vi.mocked(octopThreadsApi.list).mockReturnValueOnce(
        new Promise((resolve) => {
          complete = resolve;
        }),
      );
      const { result } = renderActions();
      act(() => result.current.navigateToAgent("agent-a"));
      expect(octopThreadsApi.list).toHaveBeenCalledWith("agent-a");
      act(() => {
        if (action === "handleNewChat") result.current.handleNewChat();
        else result.current.handleNewChatWithAgent("agent-a");
      });
      navigateMock.mockClear();

      await act(async () => {
        complete([
          {
            thread_id: THREAD,
            title: "Old chat",
            channel_type: "dashboard",
            session_key: "dashboard",
            last_active: 10,
            created_at: 1,
            is_active: true,
          },
        ]);
      });

      expect(navigateMock).not.toHaveBeenCalled();
      expect(octopThreadsApi.rebind).not.toHaveBeenCalled();
    },
  );
});

describe("handleDeleteSession", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("stays on the thread when delete is refused because a turn is active", async () => {
    const deleteSession = vi.fn().mockResolvedValue(null);
    const { result } = renderHook(
      () =>
        useChatSessionActions({
          resolvedAgentId: "agent-a",
          activeThreadId: THREAD,
          sessions: [
            {
              id: THREAD,
              name: "Live",
              threadId: THREAD,
              updatedAt: null,
              channelType: "dashboard",
            },
            {
              id: "thr_other",
              name: "Other",
              threadId: "thr_other",
              updatedAt: null,
              channelType: "dashboard",
            },
          ],
          isMobile: false,
          setActiveAgent: vi.fn(),
          setSidebarOpen: vi.fn(),
          setSelectedModel: vi.fn(),
          setHasBrowserTool: vi.fn(),
          deleteSession,
          clearMessages: vi.fn(),
          resetNavForAgentSwitch: vi.fn(),
          markInitialNavDone: vi.fn(),
        }),
      { wrapper },
    );

    let deleted: boolean | null | undefined;
    await act(async () => {
      deleted = await result.current.handleDeleteSession(THREAD, false);
    });

    expect(deleted).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});

describe("navigateToAgent", () => {
  afterEach(() => {
    removeSession(THREAD);
    removeSession(EMPTY_CHAT_SESSION_KEY);
    vi.clearAllMocks();
  });

  it("clears the new-chat view without wiping the thread being left", async () => {
    appendUserMessage(THREAD, makeMessage("m1"));
    appendUserMessage(EMPTY_CHAT_SESSION_KEY, makeMessage("draft"));

    const { result } = renderActions();
    await act(async () => {
      result.current.navigateToAgent("agent-b");
    });

    expect(getSnapshot(THREAD).messages).toHaveLength(1);
    expect(getSnapshot(EMPTY_CHAT_SESSION_KEY).messages).toHaveLength(0);
  });

  it("ignores the expert list after the composer starts creating a thread", async () => {
    let complete!: (rows: OctopThread[]) => void;
    vi.mocked(octopThreadsApi.list).mockReturnValueOnce(
      new Promise((resolve) => {
        complete = resolve;
      }),
    );
    const { result } = renderActions(vi.fn(), ({ children }) => (
      <MemoryRouter initialEntries={["/chat/agent-a"]}>
        <Link to="/chat/agent-a/__pending__">Start first turn</Link>
        {children}
      </MemoryRouter>
    ));
    act(() => result.current.navigateToAgent("agent-a"));
    navigateMock.mockClear();

    fireEvent.click(screen.getByRole("link", { name: "Start first turn" }));
    await act(async () => {
      complete([
        {
          thread_id: THREAD,
          title: "Old chat",
          channel_type: "dashboard",
          session_key: "dashboard",
          last_active: 10,
          created_at: 1,
          is_active: true,
        },
      ]);
    });

    expect(navigateMock).not.toHaveBeenCalled();
    expect(octopThreadsApi.rebind).not.toHaveBeenCalled();
  });
});
