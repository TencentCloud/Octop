import { afterEach, describe, expect, it, vi } from "vitest";
import {
  attachThread,
  getActiveTurnId,
  getSnapshot,
  onSteerRestore,
  removeSession,
  resumeHitl,
  sendSteerWhileBusy,
  setMessages,
  setSessionTeamRoom,
  withdrawCommittedSteer,
} from "./chatStore";

vi.mock("../../../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

const SESSION = "test-hitl-resume";

describe("resumeHitl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    removeSession(SESSION);
  });

  it("renders resumed tokens and notifies after the completed stream", async () => {
    const body = [
      'event: chunk\ndata: {"type":"token","content":"completed answer"}\n\n',
      'event: chunk\ndata: {"type":"done"}\n\n',
    ].join("");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );
    const onStreamEnd = vi.fn();

    await resumeHitl(
      SESSION,
      "agent-1",
      "thread-1",
      [{ type: "respond", message: "answer" }],
      onStreamEnd,
    );

    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe(
      "completed answer",
    );
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    expect(onStreamEnd).toHaveBeenCalledOnce();
  });

  it("records the session policy on the resolved card", async () => {
    setMessages(SESSION, [
      {
        id: "hitl",
        role: "assistant",
        content: "",
        timestamp: 0,
        status: "done",
        hitlData: {
          action_requests: [{ name: "execute", args: {} }],
          status: "pending",
        },
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('event: chunk\ndata: {"type":"done"}\n\n', {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    await resumeHitl(
      SESSION,
      "agent-1",
      "thread-1",
      [{ type: "approve" }],
      undefined,
      false,
      { mode: "allow_all" },
    );

    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("approved");
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.resolution).toBe(
      "allow_all",
    );
  });

  it("does not rewrite already resolved HITL cards", async () => {
    setMessages(SESSION, [
      {
        id: "old",
        role: "assistant",
        content: "",
        timestamp: 0,
        status: "done",
        hitlData: {
          action_requests: [{ name: "write_file", args: {} }],
          status: "approved",
          resolution: "approve",
        },
      },
      {
        id: "pending",
        role: "assistant",
        content: "",
        timestamp: 1,
        status: "done",
        hitlData: {
          action_requests: [{ name: "execute", args: {} }],
          status: "pending",
        },
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('event: chunk\ndata: {"type":"done"}\n\n', {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    await resumeHitl(
      SESSION,
      "agent-1",
      "thread-1",
      [{ type: "approve" }],
      undefined,
      false,
      { mode: "allow_all" },
    );

    const messages = getSnapshot(SESSION).messages;
    expect(messages[0]?.hitlData).toMatchObject({
      status: "approved",
      resolution: "approve",
    });
    expect(messages[1]?.hitlData).toMatchObject({
      status: "approved",
      resolution: "allow_all",
    });
  });

  it("keeps the member answer and the room socket when approval continues", async () => {
    setSessionTeamRoom(SESSION, true);
    const sent: string[] = [];
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
      constructor(_url: string) {
        queueMicrotask(() => {
          this.readyState = FakeSocket.OPEN;
          this.onopen?.();
        });
      }
      send(data: string) {
        sent.push(data);
      }
      close() {
        this.readyState = FakeSocket.CLOSED;
        this.onclose?.();
      }
    }
    vi.stubGlobal("WebSocket", FakeSocket);

    await attachThread(SESSION, "host", "thr-room");
    setMessages(SESSION, [
      {
        id: "member",
        role: "assistant",
        content: "磁盘还剩 8G",
        timestamp: 1,
        status: "streaming",
        speakerAgentId: "member",
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          'event: chunk\ndata: {"type":"done","team_member_continuing":true}\n\n',
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      ),
    );
    const onStreamEnd = vi.fn();

    await resumeHitl(
      SESSION,
      "host",
      "thr-room",
      [{ type: "approve" }],
      onStreamEnd,
    );

    expect(getSnapshot(SESSION).messages[0]?.content).toBe("磁盘还剩 8G");
    expect(getSnapshot(SESSION).messages[0]?.status).toBe("streaming");
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    expect(onStreamEnd).not.toHaveBeenCalled();
    expect(sent.some((frame) => frame.includes('"cancel"'))).toBe(false);
  });

  it("does not cancel a parked 1:1 socket or end the turn when approving", async () => {
    const sent: string[] = [];
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
      constructor(_url: string) {
        queueMicrotask(() => {
          this.readyState = FakeSocket.OPEN;
          this.onopen?.();
        });
      }
      send(data: string) {
        sent.push(data);
      }
      close() {
        this.readyState = FakeSocket.CLOSED;
        this.onclose?.();
      }
    }
    vi.stubGlobal("WebSocket", FakeSocket);

    const attachEnd = vi.fn();
    await attachThread(SESSION, "agent-1", "thr-one", attachEnd);
    setMessages(SESSION, [
      {
        id: "hitl",
        role: "assistant",
        content: "",
        timestamp: 1,
        status: "done",
        hitlData: {
          action_requests: [{ name: "execute", args: {} }],
          pending_id: "pend-1",
          status: "pending",
        },
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('event: chunk\ndata: {"type":"done"}\n\n', {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );
    const resumeEnd = vi.fn();

    await resumeHitl(
      SESSION,
      "agent-1",
      "thr-one",
      [{ type: "approve" }],
      resumeEnd,
      false,
      undefined,
      "pend-1",
    );

    expect(sent.some((frame) => frame.includes('"cancel"'))).toBe(false);
    expect(attachEnd).not.toHaveBeenCalled();
    expect(resumeEnd).toHaveBeenCalledOnce();
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("approved");
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
  });

  it("keeps the approved member responding and leaves the other card pending", async () => {
    setSessionTeamRoom(SESSION, true);
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
      constructor(_url: string) {
        queueMicrotask(() => {
          this.readyState = FakeSocket.OPEN;
          this.onopen?.();
        });
      }
      send(_data: string) {}
      close() {
        this.readyState = FakeSocket.CLOSED;
        this.onclose?.();
      }
    }
    vi.stubGlobal("WebSocket", FakeSocket);
    await attachThread(SESSION, "host", "thr-room");
    setMessages(SESSION, [
      {
        id: "doctor-text",
        role: "assistant",
        content: "先看磁盘",
        timestamp: 1,
        status: "streaming",
        speakerAgentId: "doctor",
      },
      {
        id: "doctor-card",
        role: "assistant",
        content: "",
        timestamp: 2,
        status: "done",
        speakerAgentId: "doctor",
        hitlData: {
          pending_id: "doc",
          action_requests: [{ name: "execute", args: {} }],
          status: "pending",
        },
      },
      {
        id: "nurse-card",
        role: "assistant",
        content: "",
        timestamp: 3,
        status: "done",
        speakerAgentId: "nurse",
        hitlData: {
          pending_id: "nur",
          action_requests: [{ name: "write_file", args: {} }],
          status: "pending",
        },
      },
    ]);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        'event: chunk\ndata: {"type":"done","team_member_continuing":true}\n\n',
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await resumeHitl(
      SESSION,
      "host",
      "thr-room",
      [{ type: "approve" }],
      undefined,
      false,
      undefined,
      "doc",
    );

    const snap = getSnapshot(SESSION);
    expect(snap.messages[0]?.status).toBe("streaming");
    expect(snap.messages[1]?.hitlData?.status).toBe("approved");
    expect(snap.messages[2]?.hitlData?.status).toBe("pending");
    expect(snap.liveSpeakers).toContain("doctor");
    expect(snap.liveSpeakers).not.toContain("nurse");
    expect(snap.isStreaming).toBe(false);
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.pending_id).toBe("doc");
  });

  function installSocket() {
    const sockets: Array<{
      readyState: number;
      onopen: (() => void) | null;
      onmessage: ((event: { data: string }) => void) | null;
      onclose: (() => void) | null;
      sent: string[];
    }> = [];
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
    return sockets;
  }

  it("keeps parked steers and skips history refresh when resume pauses again", async () => {
    const sockets = installSocket();
    await attachThread(SESSION, "agent-1", "thr-one");
    const socket = sockets[0];
    expect(socket).toBeTruthy();
    socket?.push({
      type: "turn.started",
      turn_id: "turn-1",
      thread_id: "thr-one",
    });
    expect(
      sendSteerWhileBusy(SESSION, "fix the path", {
        expectedTurnId: "turn-1",
        clientPendingId: "c1",
      }),
    ).toBe("ok");
    socket?.push({
      type: "steer.queued",
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thr-one",
      preview: "fix the path",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          [
            'event: chunk\ndata: {"type":"hitl_required","request":{"pending_id":"pend-2","action_requests":[{"name":"execute","args":{}}]}}\n\n',
            'event: chunk\ndata: {"type":"done","hitl_paused":true}\n\n',
          ].join(""),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      ),
    );
    const onStreamEnd = vi.fn();

    await resumeHitl(
      SESSION,
      "agent-1",
      "thr-one",
      [{ type: "approve" }],
      onStreamEnd,
    );

    const snap = getSnapshot(SESSION);
    expect(onStreamEnd).not.toHaveBeenCalled();
    expect(snap.isStreaming).toBe(false);
    expect(getActiveTurnId(SESSION)).toBe("turn-1");
    expect(snap.messages.some((message) => message.id === "steer:c1")).toBe(
      true,
    );
    expect(
      snap.messages.some(
        (message) => message.hitlData?.pending_id === "pend-2",
      ),
    ).toBe(true);
  });

  it("restores a withdrawn steer only after the server removes it", async () => {
    const sockets = installSocket();
    await attachThread(SESSION, "agent-1", "thr-one");
    const socket = sockets[0];
    socket?.push({
      type: "turn.started",
      turn_id: "turn-1",
      thread_id: "thr-one",
    });
    sendSteerWhileBusy(SESSION, "fix the path", {
      expectedTurnId: "turn-1",
      clientPendingId: "c1",
    });
    socket?.push({
      type: "steer.queued",
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thr-one",
      preview: "fix the path",
    });
    const restored: string[] = [];
    const stop = onSteerRestore((event) => {
      restored.push(event.reason);
    });

    expect(withdrawCommittedSteer(SESSION, "steer:c1")).toBe("ok");
    expect(restored).toEqual([]);
    expect(
      getSnapshot(SESSION).messages.some(
        (message) => message.id === "steer:c1",
      ),
    ).toBe(true);
    expect(socket?.sent.some((frame) => frame.includes("steer_remove"))).toBe(
      true,
    );

    socket?.push({
      type: "steer.ack",
      status: "removed",
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thr-one",
    });
    expect(restored).toEqual(["withdrawn"]);
    expect(
      getSnapshot(SESSION).messages.some(
        (message) => message.id === "steer:c1",
      ),
    ).toBe(false);
    stop();
  });

  it("keeps an already-drained steer in the transcript", async () => {
    const sockets = installSocket();
    await attachThread(SESSION, "agent-1", "thr-one");
    const socket = sockets[0];
    socket?.push({
      type: "turn.started",
      turn_id: "turn-1",
      thread_id: "thr-one",
    });
    sendSteerWhileBusy(SESSION, "fix the path", {
      expectedTurnId: "turn-1",
      clientPendingId: "c1",
    });
    socket?.push({
      type: "steer.queued",
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thr-one",
      preview: "fix the path",
    });
    const restored: Array<{ reason: string; applyToComposer?: boolean }> = [];
    const stop = onSteerRestore((event) => {
      restored.push({
        reason: event.reason,
        applyToComposer: event.applyToComposer,
      });
    });

    expect(withdrawCommittedSteer(SESSION, "steer:c1")).toBe("ok");
    socket?.push({
      type: "steer.ack",
      status: "removed",
      already_drained: true,
      client_pending_id: "c1",
      pending_id: "p1",
      thread_id: "thr-one",
    });

    expect(restored).toEqual([
      { reason: "already_drained", applyToComposer: false },
    ]);
    expect(
      getSnapshot(SESSION).messages.some(
        (message) => message.id === "steer:c1",
      ),
    ).toBe(true);
    stop();
  });
});
