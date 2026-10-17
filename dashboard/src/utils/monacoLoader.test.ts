import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const config = vi.fn();

vi.mock("@monaco-editor/react", () => ({ loader: { config } }));

describe("monacoLoader", () => {
  beforeEach(() => {
    vi.resetModules();
    config.mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("resolves from the site root on a deep route", async () => {
    // A relative URL would resolve under /chat/... and 404.
    window.history.pushState({}, "", "/chat/agent-1/thread-1");

    const mod = await import("./monacoLoader");

    expect(mod.monacoVsPath).toBe(`${window.location.origin}/monaco/vs`);
    expect(mod.monacoVsPath).not.toMatch(/cdn|jsdelivr|unpkg/);
  });

  it("redirects the loader when the module loads in a build", async () => {
    vi.stubEnv("DEV", false);

    const mod = await import("./monacoLoader");

    expect(config).toHaveBeenCalledWith({ paths: { vs: mod.monacoVsPath } });
  });

  it("leaves the CDN default alone in dev", async () => {
    vi.stubEnv("DEV", true);

    await import("./monacoLoader");

    expect(config).not.toHaveBeenCalled();
  });
});
