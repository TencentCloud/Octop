import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

vi.mock("../i18n", () => ({
  default: { language: "zh" },
}));

function setupRequiredResponse(): Response {
  return new Response(JSON.stringify({ setup_required: true }), {
    status: 503,
    headers: { "content-type": "application/json" },
  });
}

describe("setup lockdown handling", () => {
  const replace = vi.fn();
  let mod: typeof import("./request");
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.resetModules();
    localStorage.clear();
    replace.mockClear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/chat", replace },
    });
    fetchMock = vi.fn(() => Promise.resolve(setupRequiredResponse()));
    vi.stubGlobal("fetch", fetchMock);
    mod = await import("./request");
    mod.setAuthToken("stale-token");
    // setAuthToken clears the setup flag — re-arm a clean slate for each case.
    mod.clearSetupRequired();
  });

  it("redirects to /setup and clears the token on lockdown 503", async () => {
    await expect(mod.request("/agents")).rejects.toThrow(
      mod.SetupRequiredError,
    );

    expect(replace).toHaveBeenCalledWith("/setup");
    expect(mod.getAuthToken()).toBe("");
    expect(mod.isSetupRequiredKnown()).toBe(true);
  });

  it("skips the network after setup lockdown is known", async () => {
    await expect(mod.request("/agents")).rejects.toThrow(
      mod.SetupRequiredError,
    );
    fetchMock.mockClear();
    replace.mockClear();

    await expect(mod.request("/settings/capabilities")).rejects.toThrow(
      mod.SetupRequiredError,
    );

    expect(fetchMock).not.toHaveBeenCalled();
    // Already redirected once — no second navigation.
    expect(replace).not.toHaveBeenCalled();
  });

  it("still allows /setup/status while lockdown is known", async () => {
    mod.markSetupRequired();
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          setup_required: true,
          wizard_password_required: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const body = await mod.request<{ setup_required: boolean }>(
      "/setup/status",
    );
    expect(body.setup_required).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("does not hard-reload when already on /setup", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/setup", replace },
    });

    await expect(mod.request("/agents")).rejects.toThrow(
      mod.SetupRequiredError,
    );
    expect(replace).not.toHaveBeenCalled();
  });
});
