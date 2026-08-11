import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type FakeWorker = {
  state: string;
  postMessage: ReturnType<typeof vi.fn>;
  addEventListener: (type: string, fn: () => void) => void;
};

function mockRegistration(opts: {
  waiting?: FakeWorker | null;
  installing?: FakeWorker | null;
  controller?: { scriptURL: string } | null;
}) {
  const listeners = new Map<string, Array<() => void>>();
  const registration = {
    waiting: opts.waiting ?? null,
    installing: opts.installing ?? null,
    addEventListener: (type: string, fn: () => void) => {
      const list = listeners.get(type) ?? [];
      list.push(fn);
      listeners.set(type, list);
    },
    emit: (type: string) => {
      for (const fn of listeners.get(type) ?? []) fn();
    },
    update: vi.fn(),
  };
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      register: vi.fn().mockResolvedValue(registration),
      getRegistrations: vi.fn().mockResolvedValue([]),
      controller: opts.controller ?? null,
    },
  });
  return registration;
}

describe("registerProductionSW", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("activates a waiting worker when the page is uncontrolled", async () => {
    const waiting: FakeWorker = {
      state: "installed",
      postMessage: vi.fn(),
      addEventListener: vi.fn(),
    };
    mockRegistration({ waiting, controller: null });

    const { registerProductionSW } = await import("./sw-register");
    await registerProductionSW();

    expect(waiting.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/sw.js", {
      scope: "/",
      updateViaCache: "none",
    });
  });

  it("prompts when a waiting worker exists and the page is controlled", async () => {
    const waiting: FakeWorker = {
      state: "installed",
      postMessage: vi.fn(),
      addEventListener: vi.fn(),
    };
    mockRegistration({
      waiting,
      controller: { scriptURL: "https://x/sw.js" },
    });
    const onReady = vi.fn();
    window.addEventListener("pwa:update-ready", onReady);

    const { registerProductionSW } = await import("./sw-register");
    await registerProductionSW();

    expect(waiting.postMessage).not.toHaveBeenCalled();
    expect(onReady).toHaveBeenCalledOnce();
  });
});
