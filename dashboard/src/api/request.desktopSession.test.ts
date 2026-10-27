import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

vi.mock("../i18n", () => ({
  default: { language: "zh" },
}));

/**
 * A desktop session must survive its JWT expiring: the shell holds a device
 * credential, so the 401 path renews once and retries instead of landing on a
 * login screen the user could never fill in.
 */

function tokenExpiredResponse(): Response {
  return new Response(
    JSON.stringify({ error: { code: "TOKEN_EXPIRED", message: "expired" } }),
    { status: 401, headers: { "content-type": "application/json" } },
  );
}

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

interface Bridge {
  register: ReturnType<typeof vi.fn>;
  renew: ReturnType<typeof vi.fn>;
  revoke: ReturnType<typeof vi.fn>;
}

function installBridge(renewedToken: string | null): Bridge {
  const session = {
    register: vi.fn().mockResolvedValue(true),
    renew: vi
      .fn()
      .mockResolvedValue(
        renewedToken ? { access_token: renewedToken, expires_in: 86400 } : null,
      ),
    revoke: vi.fn().mockResolvedValue(true),
  };
  (globalThis as unknown as { octopDesktop: unknown }).octopDesktop = {
    session,
  };
  return session;
}

describe("desktop device session", () => {
  const replace = vi.fn();
  let fetchMock: ReturnType<typeof vi.fn>;
  let mod: typeof import("./request");

  beforeEach(async () => {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
    replace.mockClear();
    delete (globalThis as unknown as { octopDesktop?: unknown }).octopDesktop;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/chat", replace },
    });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    mod = await import("./request");
  });

  it("renews an expired session and retries once", async () => {
    const session = installBridge("renewed-token");
    mod.setAuthToken("stale-token");
    fetchMock
      .mockResolvedValueOnce(tokenExpiredResponse())
      .mockResolvedValueOnce(okResponse({ items: [] }));

    await expect(mod.request("/agents")).resolves.toEqual({ items: [] });

    expect(session.renew).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(mod.getAuthToken()).toBe("renewed-token");
    expect(replace).not.toHaveBeenCalled();
    // The retry must carry the new token, not the stale one.
    const retryInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect((retryInit.headers as Record<string, string>).Authorization).toBe(
      "Bearer renewed-token",
    );
  });

  it("registers the device credential on the first authenticated success", async () => {
    const session = installBridge("unused");
    mod.setAuthToken("live-token");
    // A Response body can only be read once, so give each call a fresh one.
    fetchMock.mockImplementation(() =>
      Promise.resolve(okResponse({ ok: true })),
    );

    await mod.request("/agents");
    await mod.request("/agent-groups");

    expect(session.register).toHaveBeenCalledOnce();
    expect(session.register).toHaveBeenCalledWith("live-token");
  });

  it("falls through to the login path when there is no bridge", async () => {
    mod.setAuthToken("stale-token");
    fetchMock.mockResolvedValue(tokenExpiredResponse());

    await expect(mod.request("/agents")).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(mod.getAuthToken()).toBe("");
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("does not retry a rejected login", async () => {
    const session = installBridge("renewed-token");
    const unauthorized = new Response(
      JSON.stringify({ error: { code: "AUTH_FAILED", message: "bad" } }),
      { status: 401, headers: { "content-type": "application/json" } },
    );
    fetchMock.mockResolvedValue(unauthorized);

    await expect(
      mod.request("/auth/login", { method: "POST", body: "{}" }),
    ).rejects.toThrow();
    expect(session.renew).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
