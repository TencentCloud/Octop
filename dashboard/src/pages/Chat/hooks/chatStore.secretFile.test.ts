import { afterEach, describe, expect, it, vi } from "vitest";
import {
  attachThread,
  getActiveTurnId,
  getSnapshot,
  onStreamEvent,
  removeSession,
  sendSteerWhileBusy,
  setMessages,
  submitSecretFile,
} from "./chatStore";

vi.mock("../../../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

const SESSION = "test-secret-file";

function seedPendingSecret() {
  setMessages(SESSION, [
    {
      id: "m-secret",
      role: "assistant",
      content: "",
      timestamp: 0,
      status: "done",
      hitlData: {
        action_requests: [
          {
            name: "request_secret_file",
            args: { path: "hr.token", prompt: "HR token" },
          },
        ],
        status: "pending",
        pending_id: "pend-1",
      },
    },
  ]);
}

describe("submitSecretFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    removeSession(SESSION);
  });

  it("posts the secret to the dedicated endpoint and consumes the resume stream", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          'event: chunk\ndata: {"type":"token","content":"done-answer"}\n\n' +
            'event: chunk\ndata: {"type":"done"}\n\n',
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    seedPendingSecret();

    const ok = await submitSecretFile(
      SESSION,
      "agent-1",
      "thread-1",
      "pend-1",
      "synthetic-token",
      "submit",
    );

    expect(ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/agents/agent-1/chat/secret-file/submit");
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      thread_id: "thread-1",
      pending_id: "pend-1",
      action: "submit",
      content: "synthetic-token",
    });
    const snapshot = getSnapshot(SESSION);
    expect(snapshot.messages[0].hitlData?.status).toBe("approved");
    expect(snapshot.messages.at(-1)?.content).toBe("done-answer");
    // the resumed transcript never carries the secret
    expect(JSON.stringify(snapshot.messages)).not.toContain("synthetic-token");
  });

  it("keeps the card pending on server failure so the user can retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "SECRET_WRITE_FAILED", message: "boom" },
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    seedPendingSecret();
    const onError = vi.fn();

    const ok = await submitSecretFile(
      SESSION,
      "agent-1",
      "thread-1",
      "pend-1",
      "synthetic-token",
      "submit",
      onError,
    );

    expect(ok).toBe(false);
    expect(onError).toHaveBeenCalledWith("boom");
    // still pending — not marked resolved, no second write attempt happened
    expect(getSnapshot(SESSION).messages[0].hitlData?.status).toBe("pending");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends action=cancel without content and marks the card rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('event: chunk\ndata: {"type":"done"}\n\n', {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    seedPendingSecret();

    const ok = await submitSecretFile(
      SESSION,
      "agent-1",
      "thread-1",
      "pend-1",
      "",
      "cancel",
    );

    expect(ok).toBe(true);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.action).toBe("cancel");
    expect("content" in body).toBe(false);
    expect(getSnapshot(SESSION).messages[0].hitlData?.status).toBe("rejected");
  });

  it("preserves the parked socket and queued steer when the resumed turn pauses again", async () => {
    const sockets: FakeSocket[] = [];
    class FakeSocket {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;
      readyState = FakeSocket.CONNECTING;
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;
      sent: string[] = [];
      constructor(_url: string) {
        sockets.push(this);
        queueMicrotask(() => {
          this.readyState = FakeSocket.OPEN;
          this.onopen?.();
        });
      }
      send(data: string) {
        this.sent.push(data);
      }
      close() {
        this.readyState = FakeSocket.CLOSED;
        this.onclose?.();
      }
      push(frame: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(frame) });
      }
    }
    vi.stubGlobal("WebSocket", FakeSocket);
    const attachEnd = vi.fn();
    await attachThread(SESSION, "agent-1", "thread-1", attachEnd);
    sockets[0].push({
      type: "turn.started",
      turn_id: "turn-1",
      thread_id: "thread-1",
    });
    seedPendingSecret();
    expect(
      sendSteerWhileBusy(SESSION, "continue with this file", {
        expectedTurnId: "turn-1",
        clientPendingId: "c1",
      }),
    ).toBe("ok");
    sockets[0].push({
      type: "steer.queued",
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thread-1",
      preview: "continue with this file",
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            'event: chunk\ndata: {"type":"hitl_required","request":{"pending_id":"pend-2","action_requests":[{"name":"execute","args":{}}]}}\n\n' +
              'event: chunk\ndata: {"type":"done","hitl_paused":true}\n\n',
            { status: 200, headers: { "Content-Type": "text/event-stream" } },
          ),
        ),
    );
    const onStreamEnd = vi.fn();
    const streamEvents: string[] = [];
    const stop = onStreamEvent((event) => {
      if (event.sessionId === SESSION) streamEvents.push(event.kind);
    });
    try {
      expect(
        await submitSecretFile(
          SESSION,
          "agent-1",
          "thread-1",
          "pend-1",
          "synthetic-token",
          "submit",
          undefined,
          onStreamEnd,
        ),
      ).toBe(true);
      const snapshot = getSnapshot(SESSION);
      expect(sockets[0].sent.some((frame) => frame.includes('"cancel"'))).toBe(
        false,
      );
      expect(attachEnd).not.toHaveBeenCalled();
      expect(onStreamEnd).not.toHaveBeenCalled();
      expect(streamEvents).not.toContain("streamEnd");
      expect(snapshot.isStreaming).toBe(false);
      expect(getActiveTurnId(SESSION)).toBe("turn-1");
      expect(
        snapshot.messages.some((message) => message.id === "steer:c1"),
      ).toBe(true);
      expect(
        snapshot.messages.find(
          (message) => message.hitlData?.pending_id === "pend-2",
        )?.hitlData?.status,
      ).toBe("pending");
    } finally {
      stop();
    }
  });

  it("only resolves the submitted pending card", async () => {
    seedPendingSecret();
    const original = getSnapshot(SESSION).messages[0];
    setMessages(SESSION, [
      original,
      {
        ...original,
        id: "other",
        hitlData: { ...original.hitlData!, pending_id: "other-pending" },
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response('event: chunk\ndata: {"type":"done"}\n\n'),
        ),
    );

    await submitSecretFile(
      SESSION,
      "agent-1",
      "thread-1",
      "pend-1",
      "synthetic-token",
      "submit",
    );

    expect(getSnapshot(SESSION).messages[0].hitlData?.status).toBe("approved");
    expect(getSnapshot(SESSION).messages[1].hitlData?.status).toBe("pending");
  });

  it("settles an accepted submission when the resume stream fails", async () => {
    seedPendingSecret();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.error(new Error("broken stream"));
            },
          }),
        ),
      ),
    );
    const onError = vi.fn();
    const onStreamEnd = vi.fn();

    const ok = await submitSecretFile(
      SESSION,
      "agent-1",
      "thread-1",
      "pend-1",
      "synthetic-token",
      "submit",
      onError,
      onStreamEnd,
    );

    expect(ok).toBe(true);
    expect(onError).not.toHaveBeenCalled();
    expect(onStreamEnd).toHaveBeenCalledOnce();
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    expect(getSnapshot(SESSION).messages[0].hitlData?.status).toBe("approved");
    expect(getSnapshot(SESSION).messages.at(-1)?.status).toBe("error");
  });
});
