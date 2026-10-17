import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  resetSessionStoreForTests,
  deleteSessions,
  sortSessions,
  toSession,
  useSessions,
  type Session,
} from "./useSessions";
import {
  appendUserMessage,
  getSnapshot,
  onSessionEvent,
  removeSession,
} from "./chatStore";

const listMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("../../../api/modules/octopThreads", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../../api/modules/octopThreads")
  >()),
  octopThreadsApi: {
    list: (...args: unknown[]) => listMock(...args),
    create: vi.fn(),
    delete: (...args: unknown[]) => deleteMock(...args),
    patch: vi.fn(),
    rename: vi.fn(),
    rebind: vi.fn(),
  },
  normalizeThreadArtifacts: () => [],
}));

describe("batch conversation deletion", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    listMock.mockReset();
    deleteMock.mockReset();
  });

  afterEach(() => {
    resetSessionStoreForTests();
    for (const id of ["one", "two", "three"]) removeSession(id);
  });

  it("retains failures and only clears successful conversations and their caches", async () => {
    listMock.mockResolvedValue([
      threadRow("one"),
      threadRow("two"),
      threadRow("three"),
    ]);
    deleteMock.mockImplementation(async (_agent, id) => {
      if (id === "two") throw new Error("cleanup failed");
    });
    for (const id of ["one", "two"]) {
      appendUserMessage(id, {
        id: `msg-${id}`,
        role: "user",
        content: id,
        timestamp: 1,
      });
    }
    const listener = vi.fn();
    const unsubscribe = onSessionEvent(listener);
    const { result } = renderHook(() => useSessions("agent-a"));
    await waitFor(() => expect(result.current.sessions).toHaveLength(3));

    let outcome;
    await act(async () => {
      outcome = await deleteSessions("agent-a", ["one", "two", "one"]);
    });

    expect(outcome).toEqual({ deletedIds: ["one"], failedIds: ["two"] });
    expect(deleteMock.mock.calls).toEqual([
      ["agent-a", "one", false],
      ["agent-a", "two", false],
    ]);
    expect(result.current.sessions.map((s) => s.id).sort()).toEqual([
      "three",
      "two",
    ]);
    expect(getSnapshot("one").messages).toHaveLength(0);
    expect(getSnapshot("two").messages).toHaveLength(1);
    expect(listener.mock.calls).toEqual([
      [{ kind: "sessionDeleted", agentId: "agent-a", sessionId: "one" }],
    ]);
    unsubscribe();
  });

  it("bounds requests and does not clear another expert's list after switching", async () => {
    listMock.mockImplementation(async (agentId) => [
      threadRow(agentId === "agent-a" ? "one" : "three"),
    ]);
    let finish!: () => void;
    deleteMock.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const { result, rerender } = renderHook(
      ({ agentId }) => useSessions(agentId),
      {
        initialProps: { agentId: "agent-a" },
      },
    );
    await waitFor(() => expect(result.current.sessions[0]?.id).toBe("one"));
    const pending = deleteSessions("agent-a", ["one", "two"]);
    expect(deleteMock).toHaveBeenCalledTimes(1);
    rerender({ agentId: "agent-b" });
    await waitFor(() => expect(result.current.sessions[0]?.id).toBe("three"));
    await act(async () => {
      finish();
      await pending;
    });
    expect(deleteMock.mock.calls).toEqual([
      ["agent-a", "one", false],
      ["agent-a", "two", false],
    ]);
    expect(result.current.sessions.map((s) => s.id)).toEqual(["three"]);
  });

  it("does not request deletion for an unsaved conversation", async () => {
    expect(await deleteSessions("agent-a", ["__pending__"])).toEqual({
      deletedIds: [],
      failedIds: ["__pending__"],
    });
    expect(deleteMock).not.toHaveBeenCalled();
  });

  it("loads the next conversations after deleting the entire loaded page", async () => {
    listMock
      .mockResolvedValueOnce(
        Array.from({ length: 11 }, (_, i) => threadRow(`thread-${i}`)),
      )
      .mockResolvedValueOnce([threadRow("next")]);
    const { result } = renderHook(() => useSessions("agent-a"));
    await waitFor(() => expect(result.current.sessions).toHaveLength(10));
    expect(result.current.hasMore).toBe(true);
    const ids = result.current.sessions.map((s) => s.id);
    await act(async () => {
      await deleteSessions("agent-a", ids);
    });
    expect(result.current.sessions.map((s) => s.id)).toEqual(["next"]);
    expect(result.current.hasMore).toBe(false);
  });

  it("allows retrying pagination when the post-delete refill fails", async () => {
    listMock
      .mockResolvedValueOnce(
        Array.from({ length: 11 }, (_, i) => threadRow(`thread-${i}`)),
      )
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce([threadRow("next")]);
    const { result } = renderHook(() => useSessions("agent-a"));
    await waitFor(() => expect(result.current.sessions).toHaveLength(10));
    const ids = result.current.sessions.map((s) => s.id);
    await act(async () => {
      await deleteSessions("agent-a", ids);
    });
    expect(result.current.sessions).toEqual([]);
    expect(result.current.hasMore).toBe(true);
    await act(async () => {
      await result.current.loadMoreSessions();
    });
    expect(result.current.sessions.map((s) => s.id)).toEqual(["next"]);
  });
});

function threadRow(threadId: string, agentExtra?: Partial<{ title: string }>) {
  return {
    thread_id: threadId,
    title: agentExtra?.title ?? null,
    last_active: 1,
    created_at: 1,
    channel_type: "dashboard",
    is_active: false,
    has_messages: true,
    pinned: false,
  };
}

describe("toSession / sortSessions ordering", () => {
  it("sorts empty new chats by created_at above older active ones", () => {
    const olderActive = toSession({
      thread_id: "thr_old",
      title: "old",
      last_active: 100,
      created_at: 10,
      has_messages: true,
    });
    const emptyNew = toSession({
      thread_id: "thr_new",
      title: null,
      last_active: 0,
      created_at: 200,
      has_messages: false,
    });
    expect(
      sortSessions([olderActive, emptyNew]).map((s: Session) => s.id),
    ).toEqual(["thr_new", "thr_old"]);
  });

  it("keeps pinned sessions first", () => {
    const pinned = toSession({
      thread_id: "thr_pin",
      title: "pin",
      last_active: 1,
      created_at: 1,
      pinned: true,
    });
    const recent = toSession({
      thread_id: "thr_recent",
      title: "recent",
      last_active: 999,
      created_at: 999,
    });
    expect(sortSessions([recent, pinned]).map((s) => s.id)).toEqual([
      "thr_pin",
      "thr_recent",
    ]);
  });

  it("maps turn_active and awaiting_user onto the session", () => {
    const session = toSession({
      thread_id: "thr_work",
      title: "busy",
      last_active: 1,
      turn_active: true,
      awaiting_user: true,
    });
    expect(session.turnActive).toBe(true);
    expect(session.awaitingUser).toBe(true);
  });
});

describe("useSessions agent switch", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    listMock.mockReset();
  });

  afterEach(() => {
    resetSessionStoreForTests();
  });

  it("clears previous-agent threads on the first render of a new agent", async () => {
    listMock.mockImplementation(async (agentId: string) => {
      if (agentId === "agent-a") {
        return [threadRow("thr_from_a")];
      }
      // Keep B's fetch pending so we can observe the sync clear.
      return new Promise(() => {});
    });

    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string | null }) => useSessions(agentId),
      { initialProps: { agentId: "agent-a" } },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.sessions.map((s) => s.id)).toEqual(["thr_from_a"]);
    });

    rerender({ agentId: "agent-b" });

    // Critical: no one-frame leak of agent-a's thr_* into agent-b.
    expect(result.current.sessions).toEqual([]);
    expect(result.current.loading).toBe(true);
    expect(result.current.sessions.some((s) => s.id === "thr_from_a")).toBe(
      false,
    );
  });

  it("ensureThreadInList returns unknown on probe network errors", async () => {
    listMock
      .mockResolvedValueOnce([]) // initial fetch for agent
      .mockRejectedValueOnce(new Error("network down")); // probe

    const { result } = renderHook(() => useSessions("agent-new"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let probe: string | undefined;
    await act(async () => {
      probe = await result.current.ensureThreadInList("thr_foreign");
    });
    expect(probe).toBe("unknown");
  });

  it("ensureThreadInList returns missing when probe confirms absence", async () => {
    listMock.mockResolvedValue([]);

    const { result } = renderHook(() => useSessions("agent-new"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let probe: string | undefined;
    await act(async () => {
      probe = await result.current.ensureThreadInList("thr_foreign");
    });
    expect(probe).toBe("missing");
  });

  it("ensureThreadInList returns found when the thread is already listed", async () => {
    listMock.mockResolvedValue([threadRow("thr_ok")]);

    const { result } = renderHook(() => useSessions("agent-new"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.sessions.map((s) => s.id)).toEqual(["thr_ok"]);
    });

    let probe: string | undefined;
    await act(async () => {
      probe = await result.current.ensureThreadInList("thr_ok");
    });
    expect(probe).toBe("found");
    expect(listMock).toHaveBeenCalledTimes(1);
  });
});
