import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { resetSessionStoreForTests, useSessions } from "./useSessions";
import { useChatSend } from "./useChatSend";

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

function deferred() {
  let resolve!: (value: { thread_id: string; session_key: string }) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<{ thread_id: string; session_key: string }>(
    (res, rej) => {
      resolve = res;
      reject = rej;
    },
  );
  return { promise, resolve, reject };
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={["/chat/agent-a"]}>{children}</MemoryRouter>
  );
}

function useChatHarness() {
  const location = useLocation();
  const navigate = useNavigate();
  const [, , agentId, threadId] = location.pathname.split("/");
  const sessions = useSessions(agentId || null);
  const { t } = useTranslation();
  const send = useChatSend({
    resolvedAgentId: agentId,
    activeThreadId: threadId || null,
    sessions: sessions.sessions,
    messagesLength: 0,
    selectedModel: null,
    selectedConnectors: [],
    selectedKnowledgeBaseIds: [],
    reasoningMode: "auto",
    reasoningEffort: null,
    sendMessage: vi.fn(),
    createSession: sessions.createSession,
    renameSession: sessions.renameSession,
    t,
  });
  return { ...send, ...sessions, navigate, path: location.pathname };
}

const pendingIds = new Set<string>();

beforeEach(() => {
  resetSessionStoreForTests();
  vi.spyOn(octopThreadsApi, "list").mockResolvedValue([]);
  vi.spyOn(octopThreadsApi, "rename").mockResolvedValue({ ok: true });
  vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
});

afterEach(() => {
  for (const id of [...pendingIds, "__empty__", "thr_a", "thr_b"]) {
    chatStore.removeSession(id);
  }
  pendingIds.clear();
  resetSessionStoreForTests();
  vi.restoreAllMocks();
});

describe("first-message session creation ownership", () => {
  it.each([
    ["agent-a", "first"],
    ["agent-a", "second"],
    ["agent-b", "first"],
    ["agent-b", "second"],
  ])(
    "isolates overlapping chats for %s when %s resolves first",
    async (agent, order) => {
      const first = deferred();
      const second = deferred();
      vi.spyOn(octopThreadsApi, "create")
        .mockReturnValueOnce(first.promise)
        .mockReturnValueOnce(second.promise);
      const { result } = renderHook(useChatHarness, { wrapper });
      await act(async () => {});
      act(() => {
        result.current.handleSend("private A");
      });
      const firstPending = result.current.path.split("/").at(-1)!;
      pendingIds.add(firstPending);
      act(() => {
        result.current.navigate(`/chat/${agent}`);
      });
      await act(async () => {});
      act(() => {
        result.current.handleSend("private B");
      });
      const secondPending = result.current.path.split("/").at(-1)!;
      pendingIds.add(secondPending);

      if (order === "first") {
        await act(async () => {
          first.resolve({ thread_id: "thr_a", session_key: "" });
        });
        expect(result.current.path).toBe(`/chat/${agent}/${secondPending}`);
        expect(
          result.current.sessions.some((s) => s.id === secondPending),
        ).toBe(true);
        expect(
          chatStore.getSnapshot(secondPending).messages.map((m) => m.content),
        ).toEqual(["private B"]);
        await act(async () => {
          second.resolve({ thread_id: "thr_b", session_key: "" });
        });
      } else {
        await act(async () => {
          second.resolve({ thread_id: "thr_b", session_key: "" });
        });
        await act(async () => {
          first.resolve({ thread_id: "thr_a", session_key: "" });
        });
      }

      expect(result.current.path).toBe(`/chat/${agent}/thr_b`);
      expect(
        chatStore.getSnapshot("thr_a").messages.map((m) => m.content),
      ).toEqual(["private A"]);
      expect(
        chatStore.getSnapshot("thr_b").messages.map((m) => m.content),
      ).toEqual(["private B"]);
      expect(chatStore.sendTurn).toHaveBeenCalledTimes(2);
      expect(
        vi
          .mocked(chatStore.sendTurn)
          .mock.calls.find((call) => call[0] === "thr_a")
          ?.slice(0, 3),
      ).toEqual(["thr_a", "private A", "agent-a"]);
      expect(
        vi
          .mocked(chatStore.sendTurn)
          .mock.calls.find((call) => call[0] === "thr_b")?.[2],
      ).toBe(agent);
      expect(result.current.sessions.map((s) => s.id).sort()).toEqual(
        agent === "agent-a" ? ["thr_a", "thr_b"] : ["thr_b"],
      );
    },
  );

  it.each(["agent-a", "agent-b"])(
    "keeps the newer pending chat when an older creation fails for %s",
    async (agent) => {
      const first = deferred();
      const second = deferred();
      vi.spyOn(octopThreadsApi, "create")
        .mockReturnValueOnce(first.promise)
        .mockReturnValueOnce(second.promise);
      const { result } = renderHook(useChatHarness, { wrapper });
      await act(async () => {});
      act(() => {
        result.current.handleSend("private A");
      });
      pendingIds.add(result.current.path.split("/").at(-1)!);
      act(() => {
        result.current.navigate(`/chat/${agent}`);
      });
      await act(async () => {});
      act(() => {
        result.current.handleSend("private B");
      });
      const pending = result.current.path.split("/").at(-1)!;
      pendingIds.add(pending);
      await act(async () => {
        first.reject(new Error("create failed"));
      });
      expect(result.current.path).toBe(`/chat/${agent}/${pending}`);
      expect(result.current.sessions.map((s) => s.id)).toEqual([pending]);
      expect(
        chatStore.getSnapshot(pending).messages.map((m) => m.content),
      ).toEqual(["private B"]);
      await act(async () => {
        second.resolve({ thread_id: "thr_b", session_key: "" });
      });
      expect(result.current.path).toBe(`/chat/${agent}/thr_b`);
      expect(chatStore.sendTurn).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["/chat/agent-a", "/settings"])(
    "sends an accepted first message without navigating back from %s",
    async (path) => {
      const request = deferred();
      vi.spyOn(octopThreadsApi, "create").mockReturnValueOnce(request.promise);
      const { result } = renderHook(useChatHarness, { wrapper });
      await act(async () => {});
      act(() => {
        result.current.handleSend("private A");
      });
      pendingIds.add(result.current.path.split("/").at(-1)!);
      act(() => {
        result.current.navigate(path);
      });
      await act(async () => {
        request.resolve({ thread_id: "thr_a", session_key: "" });
      });
      expect(result.current.path).toBe(path);
      expect(
        chatStore.getSnapshot("thr_a").messages.map((m) => m.content),
      ).toEqual(["private A"]);
      expect(chatStore.sendTurn).toHaveBeenCalledTimes(1);
    },
  );

  it("continues the accepted turn after the chat hook unmounts", async () => {
    const request = deferred();
    vi.spyOn(octopThreadsApi, "create").mockReturnValueOnce(request.promise);
    const { result, unmount } = renderHook(useChatHarness, { wrapper });
    await act(async () => {});
    act(() => {
      result.current.handleSend("private A");
    });
    pendingIds.add(result.current.path.split("/").at(-1)!);
    unmount();
    await act(async () => {
      request.resolve({ thread_id: "thr_a", session_key: "" });
    });
    expect(
      chatStore.getSnapshot("thr_a").messages.map((m) => m.content),
    ).toEqual(["private A"]);
    expect(chatStore.sendTurn).toHaveBeenCalledTimes(1);
  });

  it("does not clear an older accepted message when the newer creation fails", async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(octopThreadsApi, "create")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(useChatHarness, { wrapper });
    await act(async () => {});
    act(() => {
      result.current.handleSend("private A");
    });
    const olderPending = result.current.path.split("/").at(-1)!;
    pendingIds.add(olderPending);
    act(() => {
      result.current.navigate("/chat/agent-a");
    });
    act(() => {
      result.current.handleSend("private B");
    });
    pendingIds.add(result.current.path.split("/").at(-1)!);
    await act(async () => {
      second.reject(new Error("create failed"));
    });
    expect(result.current.path).toBe("/chat/agent-a");
    expect(
      chatStore.getSnapshot(olderPending).messages.map((m) => m.content),
    ).toEqual(["private A"]);
    await act(async () => {
      first.resolve({ thread_id: "thr_a", session_key: "" });
    });
    expect(result.current.path).toBe("/chat/agent-a");
    expect(
      chatStore.getSnapshot("thr_a").messages.map((m) => m.content),
    ).toEqual(["private A"]);
    expect(chatStore.sendTurn).toHaveBeenCalledTimes(1);
  });

  it.each(["__pending__", "__pending__-unique"])(
    "rejects transport sends to the temporary id %s",
    async (pendingId) => {
      vi.mocked(chatStore.sendTurn).mockRestore();
      const websocket = vi.spyOn(globalThis, "WebSocket");
      pendingIds.add(pendingId);
      await chatStore.sendTurn(
        pendingId,
        "private A",
        "agent-a",
        "",
        undefined,
        undefined,
        undefined,
        pendingId,
      );
      expect(websocket).not.toHaveBeenCalled();
      expect(
        chatStore
          .getSnapshot(pendingId)
          .messages.some((m) => m.status === "error"),
      ).toBe(true);
    },
  );

  it("resolves the pending URL when the create API succeeds immediately", async () => {
    vi.spyOn(octopThreadsApi, "create").mockResolvedValueOnce({
      thread_id: "thr_a",
      session_key: "",
    });
    const { result } = renderHook(useChatHarness, { wrapper });
    await act(async () => {
      result.current.handleSend("private A");
    });
    expect(result.current.path).toBe("/chat/agent-a/thr_a");
    expect(
      chatStore.getSnapshot("thr_a").messages.map((m) => m.content),
    ).toEqual(["private A"]);
  });
});
