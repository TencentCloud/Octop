import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { message } from "@/utils/antdMessage";
import * as chatStore from "./chatStore";
import { useChat } from "./useChat";

vi.mock("@/utils/antdMessage", () => ({
  message: { info: vi.fn(), error: vi.fn() },
}));

const thread = "cancel/thread";
const agent = "cancel/agent";
let sockets: MockSocket[];

class MockSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  readyState = 1;
  onopen = () => {};
  onmessage = (_event: { data: string }) => {};
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = 3;
  });
  constructor() {
    sockets.push(this);
  }
  emit(frame: object) {
    this.onmessage({ data: JSON.stringify(frame) });
  }
}

beforeEach(() => {
  sockets = [];
  vi.stubGlobal("BASE_URL", "");
  vi.stubGlobal("WebSocket", MockSocket);
  localStorage.setItem("auth_token", "test-token");
});

afterEach(() => {
  cleanup();
  chatStore.removeSession(thread);
  chatStore.removeSession("other-thread");
  localStorage.removeItem("auth_token");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  vi.useRealTimers();
});

it("posts without local state or a WS, using encoded ids and authorization", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(Response.json({ thread_id: thread, requested: true }));
  vi.stubGlobal("fetch", fetch);
  await chatStore.cancelStream(thread, agent);
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining(
      "/agents/cancel%2Fagent/threads/cancel%2Fthread/cancel",
    ),
    expect.objectContaining({
      method: "POST",
      signal: expect.any(AbortSignal),
      headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
    }),
  );
});

it.each(["__empty__", "__pending__", ""])(
  "does not send a placeholder thread %s",
  async (id) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(chatStore.cancelStream(id, agent)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["requested", "inactive", "failure", "timeout", "closed"])(
  "keeps the stream until server termination after %s",
  async (outcome) => {
    vi.useFakeTimers();
    const attach = chatStore.attachThread(thread, agent, thread);
    const ws = sockets[0];
    ws.onopen();
    await attach;
    ws.emit({ type: "turn_status", active: true });
    ws.emit({ type: "token", content: "working" });
    ws.emit({
      type: "usage",
      usage: { input_tokens: 10, output_tokens: 2, total_tokens: 12 },
    });
    const before = chatStore.getSnapshot(thread);
    const abort = vi.spyOn(AbortController.prototype, "abort");
    const fetch = vi.fn((_url: string, options: RequestInit) => {
      if (outcome === "timeout")
        return new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener(
            "abort",
            () => reject(new Error("timeout")),
            { once: true },
          );
        });
      if (outcome === "failure") return Promise.reject(new Error("offline"));
      return Promise.resolve(
        Response.json({ thread_id: thread, requested: outcome !== "inactive" }),
      );
    });
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useChat(thread, agent));
    if (outcome === "closed") ws.readyState = 3;
    await act(async () => {
      const first = result.current.cancelStream();
      await result.current.cancelStream();
      if (outcome === "timeout") await vi.advanceTimersByTimeAsync(10_000);
      await first;
    });
    expect(fetch).toHaveBeenCalledOnce();
    expect(abort).toHaveBeenCalledTimes(outcome === "timeout" ? 1 : 0);
    expect(ws.send).not.toHaveBeenCalledWith(
      expect.stringContaining('"cancel"'),
    );
    const after = chatStore.getSnapshot(thread);
    expect(after.isStreaming).toBe(true);
    expect(after.messages).toEqual(before.messages);
    expect(after.runUsage).toEqual(before.runUsage);
    expect(after.thinkingStartedAt).toBe(before.thinkingStartedAt);
    expect(
      outcome === "failure" || outcome === "timeout"
        ? message.error
        : message.info,
    ).toHaveBeenCalledWith(
      outcome === "failure" || outcome === "timeout"
        ? "chat.stopUnconfirmed"
        : outcome === "inactive"
        ? "chat.stopInactive"
        : "chat.stopRequested",
    );
    await act(async () => {
      if (outcome === "closed") {
        expect(sockets).toHaveLength(2);
        sockets[1].onopen();
        sockets[1].emit({ type: "turn_status", active: false });
      } else ws.emit({ type: "done" });
    });
    expect(chatStore.getSnapshot(thread).isStreaming).toBe(false);
    expect(chatStore.getSnapshot(thread).messages.at(-1)?.status).toBe("done");
  },
);

it("releases the pending flag and restores the captured thread after navigation", async () => {
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );
  const { result, rerender } = renderHook(({ id, aid }) => useChat(id, aid), {
    initialProps: { id: thread, aid: agent },
  });
  const pending = result.current.cancelStream();
  rerender({ id: "other-thread", aid: "other-agent" });
  await act(async () => {
    resolve(Response.json({ thread_id: thread, requested: true }));
    await pending;
  });
  expect(chatStore.hasLiveSocket(thread)).toBe(true);
  expect(chatStore.hasLiveSocket("other-thread")).toBe(false);
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  await result.current.cancelStream();
  expect(message.error).toHaveBeenCalledWith("chat.stopUnconfirmed");
});
