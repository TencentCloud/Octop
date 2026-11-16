import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/request", () => ({
  requestBlob: vi.fn(async () => new Blob(["img"], { type: "image/png" })),
}));

import { requestBlob } from "../api/request";
import { acquireAuthImageSrc, releaseAuthImageSrc } from "./useAuthImageSrc";

afterEach(() => {
  vi.mocked(requestBlob).mockClear();
});

describe("auth image cache", () => {
  it("keeps an idle object URL so the next mount does not refetch", async () => {
    const created: string[] = [];
    const revoked: string[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: (blob: Blob) => {
        const url = `blob:${created.length}:${blob.size}`;
        created.push(url);
        return url;
      },
      revokeObjectURL: (url: string) => {
        revoked.push(url);
      },
    });

    const first = await acquireAuthImageSrc("/api/avatar/keep");
    releaseAuthImageSrc("/api/avatar/keep");
    const second = await acquireAuthImageSrc("/api/avatar/keep");
    releaseAuthImageSrc("/api/avatar/keep");

    expect(second).toBe(first);
    expect(requestBlob).toHaveBeenCalledTimes(1);
    expect(revoked).not.toContain(first);
  });
});
