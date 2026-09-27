import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./config", () => ({ getApiUrl: (path: string) => `/api${path}` }));
vi.mock("../i18n", () => ({ default: { language: "zh" } }));

class FakeXHR {
  static latest: FakeXHR;
  status = 200;
  responseText = "{}";
  renewed: string | null = null;
  upload = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  constructor() {
    FakeXHR.latest = this;
  }
  open() {}
  setRequestHeader() {}
  getResponseHeader() {
    return this.renewed;
  }
  send() {}
  abort() {}
}

describe("late auth responses", () => {
  let mod: typeof import("./request");
  let respond: (response: Response) => void;
  const replace = vi.fn();

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
      vi.fn(() => new Promise<Response>((resolve) => (respond = resolve))),
    );
    mod = await import("./request");
  });

  const calls = [
    ["JSON", (api: typeof import("./request")) => api.request("/agents")],
    ["blob", (api: typeof import("./request")) => api.requestBlob("/agents")],
    [
      "probe",
      (api: typeof import("./request")) => api.probeAuthResource("/agents"),
    ],
    [
      "stream",
      (api: typeof import("./request")) => api.requestStream("/agents"),
    ],
  ] as const;

  it.each(calls)(
    "ignores a renewed %s response after logout",
    async (_, call) => {
      mod.setAuthToken("old");
      const pending = call(mod);
      mod.clearAuthToken();
      respond(
        new Response("{}", {
          headers: { "X-Octop-Access-Token": "renewed" },
        }),
      );
      await pending;
      expect(mod.getAuthToken()).toBe("");
    },
  );

  it.each(calls)(
    "ignores a late %s 401 after another login",
    async (_, call) => {
      mod.setAuthToken("old");
      const pending = call(mod);
      mod.setAuthToken("new");
      respond(new Response("{}", { status: 401 }));
      await expect(pending).rejects.toThrow("Unauthorized");
      expect(mod.getAuthToken()).toBe("new");
      expect(replace).not.toHaveBeenCalled();
    },
  );

  it("keeps a new session even when its JWT text matches the old one", async () => {
    mod.setAuthToken("same");
    const pending = mod.request("/agents");
    mod.clearAuthToken();
    mod.setAuthToken("same");
    respond(new Response("{}", { status: 401 }));
    await expect(pending).rejects.toThrow("Unauthorized");
    expect(mod.getAuthToken()).toBe("same");
    expect(replace).not.toHaveBeenCalled();
  });

  it("does not clear a new session for a late setup-lockdown response", async () => {
    mod.setAuthToken("old");
    const pending = mod.request("/agents");
    mod.setAuthToken("new");
    respond(new Response('{"setup_required":true}', { status: 503 }));
    await expect(pending).rejects.toThrow("Request failed: 503");
    expect(mod.getAuthToken()).toBe("new");
    expect(mod.isSetupRequiredKnown()).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it("does not clear a new session while parsing a setup-lockdown response", async () => {
    let finishParsing!: (body: unknown) => void;
    const parsed = new Promise<unknown>((resolve) => (finishParsing = resolve));
    const response = new Response('{"setup_required":true}', { status: 503 });
    const clone = vi.spyOn(response, "clone").mockReturnValue({
      json: () => parsed,
    } as Response);

    mod.setAuthToken("old");
    const pending = mod.request("/agents");
    respond(response);
    await vi.waitFor(() => expect(clone).toHaveBeenCalled());
    mod.setAuthToken("new");
    finishParsing({ setup_required: true });

    await expect(pending).rejects.toThrow("Request failed: 503");
    expect(mod.getAuthToken()).toBe("new");
    expect(mod.isSetupRequiredKnown()).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it("ignores a late upload renewal after logout", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);

    mod.setAuthToken("old");
    const pending = mod.requestUpload("/agents", new FormData());
    mod.clearAuthToken();
    const xhr = FakeXHR.latest;
    xhr.renewed = "renewed";
    xhr.onload?.();
    await pending;
    expect(mod.getAuthToken()).toBe("");
  });

  it("ignores a late upload 401 after another login", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);

    mod.setAuthToken("old");
    const pending = mod.requestUpload("/agents", new FormData());
    mod.setAuthToken("new");
    const xhr = FakeXHR.latest;
    xhr.status = 401;
    xhr.onload?.();
    await expect(pending).rejects.toThrow("Unauthorized");
    expect(mod.getAuthToken()).toBe("new");
    expect(replace).not.toHaveBeenCalled();
  });
});
