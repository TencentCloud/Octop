import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSnapshot,
  removeSession,
  resumeHitl,
  setMessages,
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
});
