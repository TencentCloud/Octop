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
const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({ message: messageMocks }));

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

function renderActions(deleteSession = vi.fn().mockResolvedValue(true)) {
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
        deleteSession,
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

describe("handleDeleteSession", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the Octop success message after confirmed deletion", async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.handleDeleteSession("another-thread");
    });

    expect(messageMocks.success).toHaveBeenCalledWith("chat.deleteSuccess");
    expect(messageMocks.error).not.toHaveBeenCalled();
  });

  it("keeps the session and reports a failed deletion", async () => {
    const { result } = renderActions(vi.fn().mockResolvedValue(false));

    await act(async () => {
      await result.current.handleDeleteSession("another-thread");
    });

    expect(messageMocks.error).toHaveBeenCalledWith("chat.deleteFailed");
    expect(messageMocks.success).not.toHaveBeenCalled();
  });
});
