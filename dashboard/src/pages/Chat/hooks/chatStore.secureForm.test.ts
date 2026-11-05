import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getSnapshot,
  removeSession,
  setMessages,
  submitSecureForm,
} from "./chatStore";

vi.mock("../../../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

const SESSION = "test-secure-form";

// Node's jsdom may expose no webstorage (experimental flag) — the auth-token
// reader touches it on every submit. Provide inert stand-ins.
function stubStorage() {
  const inert = {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
    clear: () => undefined,
  };
  vi.stubGlobal("localStorage", inert);
  vi.stubGlobal("sessionStorage", inert);
}

// Fresh Response per test: a body can only be read once.
const sseDone = () =>
  new Response('event: chunk\ndata: {"type":"done"}\n\n', {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

function pendingSecureFormMessage() {
  return {
    id: "secure-form-card",
    role: "assistant" as const,
    content: "",
    timestamp: 0,
    status: "done" as const,
    hitlData: {
      pending_id: "sf1",
      action_requests: [
        {
          name: "request_secure_form",
          args: {
            title: "Steam login",
            prompt: "Fill your Steam credentials",
            fields: [
              {
                id: "username",
                label: "Username",
                type: "text",
                required: true,
              },
              {
                id: "password",
                label: "Password",
                type: "password",
                required: true,
              },
            ],
            routing: {
              kind: "vault",
              vault_meta: { item_type: "login", title: "Steam" },
            },
          },
        },
      ],
      status: "pending" as const,
    },
  };
}

describe("submitSecureForm", () => {
  beforeEach(() => {
    stubStorage();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    removeSession(SESSION);
  });

  it("posts values plus confirmations to the dedicated endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDone());
    vi.stubGlobal("fetch", fetchMock);
    setMessages(SESSION, [pendingSecureFormMessage()]);
    const onStreamEnd = vi.fn();

    const result = await submitSecureForm(
      SESSION,
      "agent-1",
      "thread-1",
      "sf1",
      {
        action: "submit",
        values: { username: "alice", password: "hunter2-secret" },
        replaceConfirmed: true,
        saveToVault: true,
      },
      onStreamEnd,
    );

    expect(result).toEqual({ kind: "success" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/agents/agent-1/chat/secure-form/submit");
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers["Accept-Language"]).toBeDefined();
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      thread_id: "thread-1",
      pending_id: "sf1",
      action: "submit",
      values: { username: "alice", password: "hunter2-secret" },
      replace_confirmed: true,
      save_to_vault: true,
    });
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("approved");
    expect(onStreamEnd).toHaveBeenCalledOnce();
    // The values never land in the transcript.
    expect(JSON.stringify(getSnapshot(SESSION).messages)).not.toContain(
      "hunter2-secret",
    );
  });

  it("cancel omits values and confirmations and rejects the card", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDone());
    vi.stubGlobal("fetch", fetchMock);
    setMessages(SESSION, [pendingSecureFormMessage()]);

    const result = await submitSecureForm(
      SESSION,
      "agent-1",
      "thread-1",
      "sf1",
      { action: "cancel" },
    );

    expect(result).toEqual({ kind: "success" });
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.action).toBe("cancel");
    expect(body.values).toBeUndefined();
    expect(body.replace_confirmed).toBeUndefined();
    expect(body.save_to_vault).toBeUndefined();
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("rejected");
  });

  it("returns the error code and keeps the card pending on refusal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "VAULT_REPLACE_REQUIRED",
              message: "a login item titled 'Steam' already exists",
              details: { existing_vault_item_id: "vlt1" },
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    setMessages(SESSION, [pendingSecureFormMessage()]);

    const result = await submitSecureForm(
      SESSION,
      "agent-1",
      "thread-1",
      "sf1",
      {
        action: "submit",
        values: { username: "alice", password: "hunter2-secret" },
      },
    );

    expect(result).toEqual({
      kind: "error",
      code: "VAULT_REPLACE_REQUIRED",
      message: "a login item titled 'Steam' already exists",
      details: { existing_vault_item_id: "vlt1" },
    });
    expect(getSnapshot(SESSION).messages[0]?.hitlData?.status).toBe("pending");
    expect(JSON.stringify(getSnapshot(SESSION).messages)).not.toContain(
      "hunter2-secret",
    );
  });

  it("renders resumed tokens after a successful submit", async () => {
    const body = [
      'event: chunk\ndata: {"type":"token","content":"saved, continuing"}\n\n',
      'event: chunk\ndata: {"type":"secure_form_result","result":{"action":"submitted"}}\n\n',
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
    setMessages(SESSION, [pendingSecureFormMessage()]);

    await submitSecureForm(SESSION, "agent-1", "thread-1", "sf1", {
      action: "submit",
      values: { username: "alice", password: "hunter2-secret" },
    });

    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe(
      "saved, continuing",
    );
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    // The metadata frame carries ids only — values never surface.
    expect(JSON.stringify(getSnapshot(SESSION).messages)).not.toContain(
      "hunter2-secret",
    );
  });
});
