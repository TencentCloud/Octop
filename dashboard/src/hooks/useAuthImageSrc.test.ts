import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestBlob } = vi.hoisted(() => ({ requestBlob: vi.fn() }));

vi.mock("../api/request", () => ({ requestBlob }));

import {
  acquireAuthImageSrc,
  releaseAuthImageSrc,
} from "./useAuthImageSrc";

// jsdom does not implement the object-URL API.
let objectUrlSeq = 0;
const revokeObjectURL = vi.fn();

beforeEach(() => {
  requestBlob.mockReset();
  requestBlob.mockResolvedValue(new Blob(["x"], { type: "image/png" }));
  objectUrlSeq = 0;
  revokeObjectURL.mockReset();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: () => `blob:test/${(objectUrlSeq += 1)}`,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: revokeObjectURL,
  });
});

describe("useAuthImageSrc blob cache", () => {
  it("does not force cache:no-store, so the HTTP cache can serve repeats", async () => {
    await acquireAuthImageSrc("/api/agents/agent-a/avatar");
    expect(requestBlob).toHaveBeenCalledTimes(1);
    const [, options] = requestBlob.mock.calls[0];
    expect(options?.cache).not.toBe("no-store");
  });

  it("reuses the decoded blob after release + re-acquire", async () => {
    const url = "/api/agents/agent-b/avatar";
    const first = await acquireAuthImageSrc(url);
    releaseAuthImageSrc(url);

    const second = await acquireAuthImageSrc(url);
    expect(second).toBe(first);
    // The whole point of the fix: no second download on remount.
    expect(requestBlob).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it("keeps concurrent consumers on a single inflight fetch", async () => {
    const url = "/api/agents/agent-c/avatar";
    const [a, b] = await Promise.all([
      acquireAuthImageSrc(url),
      acquireAuthImageSrc(url),
    ]);
    expect(a).toBe(b);
    expect(requestBlob).toHaveBeenCalledTimes(1);

    releaseAuthImageSrc(url);
    releaseAuthImageSrc(url);
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });
});
