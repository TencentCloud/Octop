import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConnectorInstance } from "../../../api/modules/connectors";

const api = vi.hoisted(() => ({
  oauthStart: vi.fn(),
  oauthPending: vi.fn(),
}));
const toast = vi.hoisted(() => ({
  info: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));

vi.mock("../../../api/modules/connectors", () => ({ connectorsApi: api }));
vi.mock("@/utils/antdMessage", () => ({ message: toast }));

import {
  authRequiredServers,
  connectorsAwaitingAuth,
  needsAuthorization,
  pendingOutcome,
  reauthTarget,
  reportOAuthOutcome,
  runConnectorOAuth,
} from "./connectorOAuth";

function instance(overrides: Partial<ConnectorInstance>): ConnectorInstance {
  return {
    instance_id: "i1",
    kind: "custom-mcp",
    display_name: "Docs MCP",
    status: "active",
    mcp_server_name: "srv",
    has_credentials: true,
    shared: false,
    owner_user_id: 1,
    can_manage: true,
    created_at: 0,
    updated_at: 0,
    ...overrides,
  };
}

describe("pure helpers", () => {
  it("maps pending results to outcomes, treating a missing status as ok", () => {
    expect(pendingOutcome({ kind: "x", tokens: {} }).status).toBe("ok");
    expect(
      pendingOutcome({ status: "cancelled", kind: "x", tokens: {} }),
    ).toEqual({
      status: "cancelled",
    });
    expect(
      pendingOutcome({
        status: "error",
        message: "boom",
        kind: "x",
        tokens: {},
      }),
    ).toEqual({ status: "error", message: "boom" });
  });

  it("builds re-authorization targets only for custom MCP servers the user manages", () => {
    expect(reauthTarget(instance({}))).toEqual({
      type: "custom_mcp",
      server_name: "srv",
    });
    expect(reauthTarget(instance({ can_manage: false }))).toBeNull();
    expect(reauthTarget(instance({ kind: "notion" }))).toBeNull();
  });

  it("finds the connectors a failed turn is waiting for", () => {
    const list = [
      instance({ mcp_server_name: "a", auth_status: "ok" }),
      instance({
        mcp_server_name: "b",
        auth_status: "expired",
        can_manage: false,
      }),
      instance({ mcp_server_name: "c", auth_status: "required" }),
      instance({ mcp_server_name: "d" }),
    ];

    expect(needsAuthorization(list[1])).toBe(true);
    expect(needsAuthorization(list[3])).toBe(false);
    // The one the user can fix comes first.
    expect(connectorsAwaitingAuth(list).map((i) => i.mcp_server_name)).toEqual([
      "c",
      "b",
    ]);
    expect(
      connectorsAwaitingAuth(list, ["b"]).map((i) => i.mcp_server_name),
    ).toEqual(["b"]);
  });

  it("reads server names from error details", () => {
    expect(
      authRequiredServers({
        connectors: [{ server: "a" }, { server: "" }, null],
      }),
    ).toEqual(["a"]);
    expect(authRequiredServers(undefined)).toEqual([]);
    expect(authRequiredServers({ connectors: "x" })).toEqual([]);
  });

  it("reports each unsuccessful outcome once", () => {
    const t = ((key: string) => key) as never;
    reportOAuthOutcome({ status: "cancelled" }, t);
    reportOAuthOutcome({ status: "error", message: "denied" }, t);
    reportOAuthOutcome({ status: "timeout" }, t);
    reportOAuthOutcome({ status: "ok", result: { kind: "x", tokens: {} } }, t);
    expect(toast.info).toHaveBeenCalledWith("connectors.oauthCancelled");
    expect(toast.error).toHaveBeenCalledWith("denied");
    expect(toast.error).toHaveBeenCalledWith("connectors.oauthTimedOut");
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("runConnectorOAuth", () => {
  const originalOpen = window.open;
  let popup: {
    closed: boolean;
    close: ReturnType<typeof vi.fn>;
    location: { replace: ReturnType<typeof vi.fn> };
    focus: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.useFakeTimers();
    popup = {
      closed: false,
      close: vi.fn(),
      location: { replace: vi.fn() },
      focus: vi.fn(),
    };
    window.open = vi.fn(() => popup) as unknown as typeof window.open;
    api.oauthStart.mockResolvedValue({
      authorize_url: "https://idp.example/authorize",
      state_id: "s1",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    window.open = originalOpen;
    vi.clearAllMocks();
  });

  it("opens the popup before anything async and resolves when the callback posts back", async () => {
    api.oauthPending.mockResolvedValue({
      status: "ok",
      kind: "custom-mcp",
      tokens: {},
      applied: true,
    });
    const done = runConnectorOAuth({
      type: "custom_mcp",
      server_name: "srv",
    });
    expect(window.open).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(0);
    expect(popup.location.replace).toHaveBeenCalledWith(
      "https://idp.example/authorize",
    );
    // A message from another origin or another flow is ignored.
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "https://evil.example",
        data: { type: "octop:connector-oauth", state_id: "s1" },
      }),
    );
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: window.location.origin,
        data: { type: "octop:connector-oauth", state_id: "other" },
      }),
    );
    expect(api.oauthPending).not.toHaveBeenCalled();
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: window.location.origin,
        data: { type: "octop:connector-oauth", state_id: "s1" },
      }),
    );

    const outcome = await done;
    expect(outcome.status).toBe("ok");
    expect(api.oauthPending).toHaveBeenCalledWith("s1");
    expect(popup.close).toHaveBeenCalled();
    expect(api.oauthStart.mock.calls[0][1]).toBe(window.location.pathname);
  });

  it("polls when the popup cannot post back, and reports a cancel", async () => {
    api.oauthPending
      .mockRejectedValueOnce(new Error("404"))
      .mockResolvedValueOnce({
        status: "cancelled",
        kind: "custom-mcp",
        tokens: {},
      });
    const done = runConnectorOAuth(
      Promise.resolve({ type: "custom_mcp", server_name: "srv" }),
    );

    await vi.advanceTimersByTimeAsync(1500);
    await vi.advanceTimersByTimeAsync(1500);

    await expect(done).resolves.toEqual({ status: "cancelled" });
  });

  it("times out", async () => {
    api.oauthPending.mockRejectedValue(new Error("404"));
    const done = runConnectorOAuth(
      { type: "custom_mcp", server_name: "srv" },
      { timeoutMs: 4000 },
    );

    await vi.advanceTimersByTimeAsync(4000);

    await expect(done).resolves.toEqual({ status: "timeout" });
    expect(popup.close).toHaveBeenCalled();
  });

  it("returns the server's message when the flow cannot start", async () => {
    api.oauthStart.mockRejectedValue(
      new Error(
        '409 {"error":{"code":"CONNECTOR_NOT_FOUND","message":"connector not found"}}',
      ),
    );

    await expect(
      runConnectorOAuth({ type: "custom_mcp", server_name: "gone" }),
    ).resolves.toEqual({ status: "error", message: "connector not found" });
  });

  it("does not start when the popup is blocked", async () => {
    window.open = vi.fn(() => null) as unknown as typeof window.open;

    await expect(
      runConnectorOAuth({ type: "custom_mcp", server_name: "srv" }),
    ).resolves.toEqual({ status: "blocked" });
    expect(api.oauthStart).not.toHaveBeenCalled();
  });
});
