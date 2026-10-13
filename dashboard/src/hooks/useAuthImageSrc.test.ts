import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { requestBlobMock } = vi.hoisted(() => ({
  requestBlobMock: vi.fn(),
}));

vi.mock("../api/request", () => ({
  requestBlob: requestBlobMock,
}));

describe("auth image cache", () => {
  let nextObjectUrl = 0;

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
    requestBlobMock.mockReset();
    requestBlobMock.mockResolvedValue(
      new Blob(["image"], { type: "image/png" }),
    );
    nextObjectUrl = 0;
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => `blob:test-${nextObjectUrl++}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reuses an idle object URL when an image remounts", async () => {
    const { acquireAuthImageSrc, releaseAuthImageSrc } = await import(
      "./useAuthImageSrc"
    );
    const url = "/api/agents/agent-1/avatar?v=1";

    const first = await acquireAuthImageSrc(url);
    releaseAuthImageSrc(url);
    const second = await acquireAuthImageSrc(url);

    expect(second).toBe(first);
    expect(requestBlobMock).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    releaseAuthImageSrc(url);
  });

  it("refetches and revokes an idle object URL after five minutes", async () => {
    const { acquireAuthImageSrc, releaseAuthImageSrc } = await import(
      "./useAuthImageSrc"
    );
    const url = "/api/agents/agent-2/avatar?v=1";

    const first = await acquireAuthImageSrc(url);
    releaseAuthImageSrc(url);
    vi.advanceTimersByTime(5 * 60 * 1000 + 1);
    const second = await acquireAuthImageSrc(url);

    expect(second).not.toBe(first);
    expect(requestBlobMock).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(first);
    releaseAuthImageSrc(url);
  });

  it("evicts the least recently used idle entry when the cache exceeds 50", async () => {
    const { acquireAuthImageSrc, releaseAuthImageSrc } = await import(
      "./useAuthImageSrc"
    );

    for (let index = 0; index <= 50; index += 1) {
      const url = `/api/agents/agent-${index}/avatar?v=1`;
      await acquireAuthImageSrc(url);
      releaseAuthImageSrc(url);
      vi.advanceTimersByTime(1);
    }

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-0");
    await acquireAuthImageSrc("/api/agents/agent-0/avatar?v=1");
    expect(requestBlobMock).toHaveBeenCalledTimes(52);
  });
});
