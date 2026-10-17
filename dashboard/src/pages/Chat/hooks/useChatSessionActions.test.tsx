import { renderHook, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { useChatSessionActions } from "./useChatSessionActions";
import {
  appendUserMessage,
  getSnapshot,
  removeSession,
  type ChatMessage,
} from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY } from "../constants";
import { toSession, resetSessionStoreForTests } from "./useSessions";

const navigateMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../../api/modules/octopThreads", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../../api/modules/octopThreads")
  >()),
  octopThreadsApi: {
    delete: (...args: unknown[]) => deleteMock(...args),
    rebind: vi.fn().mockResolvedValue({}),
    list: vi.fn().mockResolvedValue([]),
  },
}));

describe("batch deletion navigation", () => {
  afterEach(() => {
    vi.clearAllMocks();
    deleteMock.mockReset();
    resetSessionStoreForTests();
  });

  function setup() {
    const clearMessages = vi.fn();
    const sessions = ["one", "two", "three"].map((id) =>
      toSession({
        thread_id: id,
        title: id,
        last_active: 1,
      }),
    );
    const hook = renderHook(
      ({ agentId, threadId }) =>
        useChatSessionActions({
          resolvedAgentId: agentId,
          activeThreadId: threadId,
          sessions,
          isMobile: false,
          setActiveAgent: vi.fn(),
          setSidebarOpen: vi.fn(),
          setSelectedModel: vi.fn(),
          setHasBrowserTool: vi.fn(),
          deleteSession: vi.fn(),
          clearMessages,
          resetNavForAgentSwitch: vi.fn(),
          markInitialNavDone: vi.fn(),
        }),
      { wrapper, initialProps: { agentId: "agent-a", threadId: "one" } },
    );
    return { ...hook, clearMessages };
  }

  it("navigates once to a survivor, never to another deleted conversation", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.handleBatchDeleteSessions("agent-a", ["one", "two"]);
    });
    expect(navigateMock.mock.calls).toEqual([
      ["/chat/agent-a/three", { replace: true }],
    ]);
  });

  it("shows a new conversation after deleting all conversations", async () => {
    const { result, clearMessages } = setup();
    await act(async () => {
      await result.current.handleBatchDeleteSessions("agent-a", [
        "one",
        "two",
        "three",
      ]);
    });
    expect(navigateMock).toHaveBeenCalledWith("/chat/agent-a", {
      replace: true,
    });
    expect(clearMessages).toHaveBeenCalledOnce();
  });

  it("does not return to chat after leaving the page during deletion", async () => {
    let finish!: () => void;
    deleteMock.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const { result, unmount, clearMessages } = setup();
    const pending = result.current.handleBatchDeleteSessions("agent-a", [
      "one",
    ]);
    unmount();
    await act(async () => {
      finish();
      await pending;
    });
    expect(navigateMock).not.toHaveBeenCalled();
    expect(clearMessages).not.toHaveBeenCalled();
  });

  it("stays on the active conversation when its deletion fails", async () => {
    deleteMock.mockImplementation(async (_agent, id) => {
      if (id === "one") throw new Error("failed");
    });
    const { result, clearMessages } = setup();
    await act(async () => {
      await result.current.handleBatchDeleteSessions("agent-a", ["one", "two"]);
    });
    expect(navigateMock).not.toHaveBeenCalled();
    expect(clearMessages).not.toHaveBeenCalled();
  });

  it.each([
    { agentId: "agent-b", threadId: "one" },
    { agentId: "agent-a", threadId: "three" },
  ])(
    "does not override navigation to $agentId/$threadId during a batch",
    async (next) => {
      let finish!: () => void;
      deleteMock.mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            finish = resolve;
          }),
      );
      const { result, rerender } = setup();
      const pending = result.current.handleBatchDeleteSessions("agent-a", [
        "one",
        "two",
      ]);
      rerender(next);
      await act(async () => {
        finish();
        await pending;
      });
      expect(navigateMock).not.toHaveBeenCalled();
    },
  );
});

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

const THREAD = "thr_leaving";

function makeMessage(id: string): ChatMessage {
  return { id, role: "user", content: `message ${id}`, timestamp: Date.now() };
}

function renderActions() {
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
        markInitialNavDone: vi.fn(),
      }),
    { wrapper },
  );
}

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
});
