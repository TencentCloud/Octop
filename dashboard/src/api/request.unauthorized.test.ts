import { beforeEach, describe, expect, it, vi } from "vitest";
import { isUnauthorizedExemptPath } from "./request";

vi.mock("./config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

vi.mock("../i18n", () => ({
  default: { language: "zh" },
}));

function unauthorizedResponse(): Response {
  return new Response("{}", {
    status: 401,
    headers: { "content-type": "application/json" },
  });
}

describe("401 handling", () => {
  const replace = vi.fn();
  let mod: typeof import("./request");

  beforeEach(async () => {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
    replace.mockClear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/chat", replace },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(unauthorizedResponse())),
    );
    mod = await import("./request");
    mod.setAuthToken("expired-token");
  });

  it("lets an in-app listener take over the redirect instead of reloading", async () => {
    const listener = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener(mod.UNAUTHORIZED_EVENT, listener);

    await expect(mod.request("/agents")).rejects.toThrow();

    expect(listener).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();
    expect(mod.getAuthToken()).toBe("");

    window.removeEventListener(mod.UNAUTHORIZED_EVENT, listener);
  });

  it("falls back to a full-page navigation when nothing handles the event", async () => {
    await expect(mod.request("/agents")).rejects.toThrow();

    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("redirects only once when several requests fail concurrently", async () => {
    const listener = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener(mod.UNAUTHORIZED_EVENT, listener);

    await Promise.allSettled([
      mod.request("/agents"),
      mod.request("/skills"),
      mod.request("/cron"),
    ]);

    expect(listener).toHaveBeenCalledOnce();

    window.removeEventListener(mod.UNAUTHORIZED_EVENT, listener);
  });

  it("does not clear token or redirect for probe 401 responses", async () => {
    const listener = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener(mod.UNAUTHORIZED_EVENT, listener);

    await expect(
      mod.request("/bridge/probe", {
        method: "POST",
        body: JSON.stringify({ peer_base_url: "http://peer", peer_username: "u", password: "p" }),
      }),
    ).rejects.toThrow();

    // Probe 401 must not trigger session eviction or logout navigation
    expect(listener).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(mod.getAuthToken()).toBe("expired-token");

    window.removeEventListener(mod.UNAUTHORIZED_EVENT, listener);
  });
});

describe("isUnauthorizedExemptPath", () => {
  it("exempts /auth/ endpoints", () => {
    expect(isUnauthorizedExemptPath("/auth/login")).toBe(true);
    expect(isUnauthorizedExemptPath("/auth/ldap/login")).toBe(true);
    expect(isUnauthorizedExemptPath("/auth/refresh")).toBe(true);
  });

  it("exempts /probe endpoints across all modules", () => {
    expect(isUnauthorizedExemptPath("/bridge/probe")).toBe(true);
    expect(isUnauthorizedExemptPath("/bridge/connections/c1/probe")).toBe(true);
    expect(isUnauthorizedExemptPath("/filesystem/probe")).toBe(true);
    expect(isUnauthorizedExemptPath("/agents/a1/channels/probe")).toBe(true);
    expect(isUnauthorizedExemptPath("/storage-backends/probe")).toBe(true);
  });

  it("does not exempt standard resource paths", () => {
    expect(isUnauthorizedExemptPath("/agents")).toBe(false);
    expect(isUnauthorizedExemptPath("/bridge/connections")).toBe(false);
    expect(isUnauthorizedExemptPath("/chat/conversations")).toBe(false);
    expect(isUnauthorizedExemptPath("/users/me")).toBe(false);
  });
});
