import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../request", () => ({
  request: vi.fn(),
  getAuthToken: () => "test-token",
}));

vi.mock("../config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));

import { mobileApi } from "./mobile";

interface StubReader {
  read: () => Promise<{ done: boolean; value?: Uint8Array }>;
}

function sseBody(chunks: string[]): { getReader: () => StubReader } {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    getReader: () => ({
      read: async () => {
        if (index >= chunks.length) return { done: true };
        const value = encoder.encode(chunks[index]);
        index += 1;
        return { done: false, value };
      },
    }),
  };
}

function sseResponse(chunks: string[], status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    body: sseBody(chunks),
  } as unknown as Response;
}

function stubFetch(chunks: string[], status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => sseResponse(chunks, status)),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mobileApi.install", () => {
  it("reports failure when the body closes without a terminal frame", async () => {
    stubFetch(['data: {"log":"installing adb"}\n\n']);
    const logs: string[] = [];
    const onDone = vi.fn();

    mobileApi.install((line) => logs.push(line), onDone);

    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(logs).toEqual(["installing adb"]);
    expect(onDone).toHaveBeenCalledWith(false, expect.any(String));
  });

  it("settles once even when a terminal frame is followed by another frame", async () => {
    stubFetch([
      'data: {"done":true}\n\n',
      'data: {"done":false,"error":"boom"}\n\n',
    ]);
    const onDone = vi.fn();

    mobileApi.install(() => {}, onDone);

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone.mock.calls[0]?.[0]).toBe(true);
  });

  it("reports the terminal success frame together with its log line", async () => {
    stubFetch(['data: {"log":"ok","done":true}\n\n']);
    const logs: string[] = [];
    const onDone = vi.fn();

    mobileApi.install((line) => logs.push(line), onDone);

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDone.mock.calls[0]?.[0]).toBe(true);
    expect(logs).toEqual(["ok"]);
  });

  it("reports a non-2xx response instead of hanging", async () => {
    stubFetch([], 500);
    const onDone = vi.fn();

    mobileApi.install(() => {}, onDone);

    await vi.waitFor(() =>
      expect(onDone).toHaveBeenCalledWith(false, "HTTP 500"),
    );
  });
});
