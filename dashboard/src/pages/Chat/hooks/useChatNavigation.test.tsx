import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { useChatNavigation } from "./useChatNavigation";
import type { Session } from "./useSessions";

const navigateMock = vi.fn();
const rebindMock = vi.fn().mockResolvedValue({});

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: {
    rebind: (...args: unknown[]) => rebindMock(...args),
  },
}));

vi.mock("../../../api/modules/octopAgents", () => ({
  octopAgentsApi: {
    markRead: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("./chatStore", () => ({
  getSnapshot: () => ({ messages: [], isStreaming: false }),
  onStreamEvent: () => () => undefined,
}));

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

function session(id: string): Session {
  return {
    id,
    name: "Chat",
    threadId: id,
    updatedAt: null,
    channelType: "dashboard",
    hasActivity: true,
  };
}

describe("useChatNavigation stale thread", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    rebindMock.mockReset().mockResolvedValue({});
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("rewrites URL only after ensureThreadInList confirms missing", async () => {
    const ensureThreadInList = vi.fn().mockResolvedValue("missing");
    const prefillInputRef = { current: "" };

    renderHook(
      () =>
        useChatNavigation({
          routeAgentId: "agent-new",
          threadId: "thr_foreign",
          resolvedAgentId: "agent-new",
          activeThreadId: "thr_foreign",
          sessions: [],
          sessionsLoading: false,
          prefillInputRef,
          loadHistory: vi.fn().mockResolvedValue(undefined),
          clearMessages: vi.fn(),
          ensureThreadInList,
          fetchSessions: vi.fn().mockResolvedValue([]),
          refreshAgents: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(ensureThreadInList).toHaveBeenCalledWith("thr_foreign");
      expect(navigateMock).toHaveBeenCalledWith("/chat/agent-new", {
        replace: true,
      });
    });
  });

  it("does not rewrite URL when probe result is unknown", async () => {
    const ensureThreadInList = vi.fn().mockResolvedValue("unknown");
    const prefillInputRef = { current: "" };

    renderHook(
      () =>
        useChatNavigation({
          routeAgentId: "agent-new",
          threadId: "thr_maybe",
          resolvedAgentId: "agent-new",
          activeThreadId: "thr_maybe",
          sessions: [],
          sessionsLoading: false,
          prefillInputRef,
          loadHistory: vi.fn().mockResolvedValue(undefined),
          clearMessages: vi.fn(),
          ensureThreadInList,
          fetchSessions: vi.fn().mockResolvedValue([]),
          refreshAgents: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(ensureThreadInList).toHaveBeenCalledWith("thr_maybe");
    });
    expect(navigateMock).not.toHaveBeenCalledWith(
      "/chat/agent-new",
      expect.anything(),
    );
  });

  it("does not rewrite URL when probe finds the thread", async () => {
    const ensureThreadInList = vi.fn().mockResolvedValue("found");
    const prefillInputRef = { current: "" };

    renderHook(
      () =>
        useChatNavigation({
          routeAgentId: "agent-new",
          threadId: "thr_ok",
          resolvedAgentId: "agent-new",
          activeThreadId: "thr_ok",
          sessions: [],
          sessionsLoading: false,
          prefillInputRef,
          loadHistory: vi.fn().mockResolvedValue(undefined),
          clearMessages: vi.fn(),
          ensureThreadInList,
          fetchSessions: vi.fn().mockResolvedValue([]),
          refreshAgents: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(ensureThreadInList).toHaveBeenCalledWith("thr_ok");
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("prefers an existing session when the URL thread is missing", async () => {
    const ensureThreadInList = vi.fn().mockResolvedValue("missing");
    const prefillInputRef = { current: "" };
    const sessions = [session("thr_ok")];

    renderHook(
      () =>
        useChatNavigation({
          routeAgentId: "agent-a",
          threadId: "thr_gone",
          resolvedAgentId: "agent-a",
          activeThreadId: "thr_gone",
          sessions,
          sessionsLoading: false,
          prefillInputRef,
          loadHistory: vi.fn().mockResolvedValue(undefined),
          clearMessages: vi.fn(),
          ensureThreadInList,
          fetchSessions: vi.fn().mockResolvedValue(sessions),
          refreshAgents: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/chat/agent-a/thr_ok", {
        replace: true,
      });
    });
  });
});
