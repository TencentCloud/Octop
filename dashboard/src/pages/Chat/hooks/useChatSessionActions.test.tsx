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

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: {
    rebind: vi.fn().mockResolvedValue({}),
    list: vi.fn().mockResolvedValue([]),
  },
}));

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
});
