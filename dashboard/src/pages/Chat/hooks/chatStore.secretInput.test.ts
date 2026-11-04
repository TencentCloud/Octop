import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSnapshot,
  removeSession,
  setMessages,
  submitSecretInput,
} from "./chatStore";

vi.mock("../../../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

const SESSION = "test-secret-input";

// Fresh Response per test: a body can only be read once.
const sseDone = () =>
  new Response('event: chunk\ndata: {"type":"done"}\n\n', {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

function pendingSecretMessage() {
  return {
    id: "secret-card",
    role: "assistant" as const,
    content: "",
    timestamp: 0,
    status: "done" as const,
    hitlData: {
      pending_id: "sec1",
      action_requests: [
        {
          name: "request_secret_input",
          args: { slot: "STEAM_WEB_API_KEY", prompt: "Steam key" },
        },
      ],
      status: "pending" as const,
    },
  };
}

describe("submitSecretInput", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    removeSession(SESSION);
  });

  it("posts to the dedicated endpoint and resolves the card on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDone());
    vi.stubGlobal("fetch", fetchMock);
    setMessages(SESSION, [pendingSecretMessage()]);
    const onStreamEnd = vi.fn();

    const result = await submitSecretInput(
      SESSION,
      "agent-1",
      "thread-1",
      "sec1",
      "submit",
      onStreamEnd,
      "sk-secret-value",
    );

    expect(result).toBeNull();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/agents/agent-1/chat/secret-input/submit");
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      thread_id: "thread-1",
      pending_id: "sec1",
      action: "submit",
      value: "sk-secret-value",
    });
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("approved");
    expect(onStreamEnd).toHaveBeenCalledOnce();
    // The secret never lands in the transcript.
    expect(JSON.stringify(getSnapshot(SESSION).messages)).not.toContain(
      "sk-secret-value",
    );
  });

  it("cancel omits the value and marks the card rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDone());
    vi.stubGlobal("fetch", fetchMock);
    setMessages(SESSION, [pendingSecretMessage()]);

    const result = await submitSecretInput(
      SESSION,
      "agent-1",
      "thread-1",
      "sec1",
      "cancel",
    );

    expect(result).toBeNull();
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.action).toBe("cancel");
    expect(body.value).toBeUndefined();
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("rejected");
  });

  it("returns the server error and keeps the card pending on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "SECRET_REQUEST_INVALID", message: "stale request" },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    setMessages(SESSION, [pendingSecretMessage()]);

    const result = await submitSecretInput(
      SESSION,
      "agent-1",
      "thread-1",
      "sec1",
      "submit",
      undefined,
      "sk-secret-value",
    );

    expect(result).toBe("stale request");
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("pending");
  });

  it("renders resumed tokens after a successful submit", async () => {
    const body = [
      'event: chunk\ndata: {"type":"token","content":"stored, continuing"}\n\n',
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
    setMessages(SESSION, [pendingSecretMessage()]);

    await submitSecretInput(
      SESSION,
      "agent-1",
      "thread-1",
      "sec1",
      "submit",
      undefined,
      "sk-secret-value",
    );

    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe(
      "stored, continuing",
    );
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
  });
});
