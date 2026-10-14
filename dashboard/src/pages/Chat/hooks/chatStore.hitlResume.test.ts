import { afterEach, describe, expect, it, vi } from "vitest";
import {
  attachThread,
  getSnapshot,
  removeSession,
  resumeHitl,
  setMessages,
  setSessionTeamRoom,
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
});
