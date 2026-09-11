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

type StoreSessionEvent = { kind: string; sessionId: string; agentId?: string };
const sessionListenerRef: {
  current: ((event: StoreSessionEvent) => void) | null;
} = { current: null };
const invalidateHistoryMock = vi.fn();

vi.mock("./chatStore", () => ({
  getSnapshot: () => ({ messages: [], isStreaming: false }),
  onStreamEvent: () => () => undefined,
  onSessionEvent: (listener: (event: StoreSessionEvent) => void) => {
    sessionListenerRef.current = listener;
    return () => {
      sessionListenerRef.current = null;
    };
  },
  invalidateHistory: (...args: unknown[]) => invalidateHistoryMock(...args),
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

describe("useChatNavigation proactive session events", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    rebindMock.mockReset().mockResolvedValue({});
    invalidateHistoryMock.mockReset();
    sessionListenerRef.current = null;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function renderWithMocks(
    loadHistory: ReturnType<typeof vi.fn>,
    fetchSessions: ReturnType<typeof vi.fn>,
  ) {
    const prefillInputRef = { current: "" };
    return renderHook(
      () =>
        useChatNavigation({
          routeAgentId: "agent-a",
          threadId: "thr_open",
          resolvedAgentId: "agent-a",
          activeThreadId: "thr_open",
          sessions: [session("thr_open")],
          sessionsLoading: false,
          prefillInputRef,
          loadHistory,
          clearMessages: vi.fn(),
          ensureThreadInList: vi.fn().mockResolvedValue("found"),
          fetchSessions,
          refreshAgents: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper },
    );
  }

  it("reloads history when the open thread changed server-side", async () => {
    const loadHistory = vi.fn().mockResolvedValue(undefined);
    const fetchSessions = vi.fn().mockResolvedValue([session("thr_open")]);
    renderWithMocks(loadHistory, fetchSessions);

    await waitFor(() => expect(sessionListenerRef.current).toBeTruthy());
    loadHistory.mockClear();
    fetchSessions.mockClear();

    sessionListenerRef.current?.({
      kind: "sessionsChanged",
      sessionId: "thr_open",
      agentId: "agent-a",
    });

    await waitFor(() => {
      expect(fetchSessions).toHaveBeenCalledWith("thr_open");
      expect(invalidateHistoryMock).toHaveBeenCalledWith("thr_open");
      expect(loadHistory).toHaveBeenCalledWith("thr_open");
    });
  });

  it("refreshes the list but not history for another thread", async () => {
    const loadHistory = vi.fn().mockResolvedValue(undefined);
    const fetchSessions = vi.fn().mockResolvedValue([session("thr_open")]);
    renderWithMocks(loadHistory, fetchSessions);

    await waitFor(() => expect(sessionListenerRef.current).toBeTruthy());
    loadHistory.mockClear();
    fetchSessions.mockClear();

    sessionListenerRef.current?.({
      kind: "sessionsChanged",
      sessionId: "thr_other",
      agentId: "agent-a",
    });

    await waitFor(() => {
      expect(fetchSessions).toHaveBeenCalledWith("thr_open");
    });
    expect(invalidateHistoryMock).not.toHaveBeenCalled();
    expect(loadHistory).not.toHaveBeenCalled();
  });

  it("ignores events for another agent and plain deletions", async () => {
    const loadHistory = vi.fn().mockResolvedValue(undefined);
    const fetchSessions = vi.fn().mockResolvedValue([session("thr_open")]);
    renderWithMocks(loadHistory, fetchSessions);

    await waitFor(() => expect(sessionListenerRef.current).toBeTruthy());
    loadHistory.mockClear();
    fetchSessions.mockClear();

    sessionListenerRef.current?.({
      kind: "sessionsChanged",
      sessionId: "thr_open",
      agentId: "agent-b",
    });
    sessionListenerRef.current?.({
      kind: "sessionDeleted",
      sessionId: "thr_open",
    });

    expect(fetchSessions).not.toHaveBeenCalled();
    expect(invalidateHistoryMock).not.toHaveBeenCalled();
    expect(loadHistory).not.toHaveBeenCalled();
  });
});
