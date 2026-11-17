import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../i18n", () => ({ default: { language: "en" } }));

const originalLocation = window.location;
const replace = vi.fn();
let api: typeof import("./request");

function location(pathname: string) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { pathname, replace },
  });
}

beforeEach(() => {
  vi.resetModules();
  replace.mockClear();
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("BASE_URL", "");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
});

describe.each(["/", "/octop/", "/tools/octop/"])(
  "auth recovery under %s",
  (base) => {
    const scenarios = [
      { status: 401, body: {}, target: "login" },
      { status: 503, body: { setup_required: true }, target: "setup" },
    ];

    beforeEach(async () => {
      vi.stubEnv("BASE_URL", base);
      location(`${base}chat/expert/thread`);
      api = await import("./request");
      api.setAuthToken("expired-test-token");
    });

    it.each(scenarios)(
      "keeps $status recovery within the application and clears credentials",
      async ({ status, body, target }) => {
        const fetch = vi.fn<typeof globalThis.fetch>(
          async () =>
            new Response(JSON.stringify(body), {
              status,
              headers: { "content-type": "application/json" },
            }),
        );
        vi.stubGlobal("fetch", fetch);
        await expect(api.request("/agents")).rejects.toThrow();
        expect(fetch.mock.calls[0]?.[0]).toBe(`${base}api/agents`);
        expect(replace).toHaveBeenCalledOnce();
        expect(replace).toHaveBeenCalledWith(`${base}${target}`);
        expect(api.getAuthToken()).toBe("");
      },
    );

    it.each(["login", "login/oidc-complete", "setup", "invite/code"])(
      "does not reload an existing %s page after an expired-session response",
      async (page) => {
        location(`${base}${page}`);
        vi.stubGlobal(
          "fetch",
          vi.fn(async () => new Response("{}", { status: 401 })),
        );
        await expect(api.request("/agents")).rejects.toThrow();
        expect(replace).not.toHaveBeenCalled();
        expect(api.getAuthToken()).toBe("");
      },
    );

    it("does not reload the prefixed wizard after a lockdown response", async () => {
      location(`${base}setup`);
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(JSON.stringify({ setup_required: true }), {
              status: 503,
            }),
        ),
      );
      await expect(api.request("/agents")).rejects.toThrow(
        api.SetupRequiredError,
      );
      expect(replace).not.toHaveBeenCalled();
    });
  },
);
