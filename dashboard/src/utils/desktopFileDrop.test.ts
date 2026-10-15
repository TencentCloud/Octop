import { afterEach, describe, expect, it, vi } from "vitest";
import { filesFromDesktopDrop } from "./desktopFileDrop";

describe("filesFromDesktopDrop", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds File objects from the loopback URLs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        expect(url).toBe("http://127.0.0.1:1/drop/token/0");
        return new Response("hello", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }),
    );

    const files = await filesFromDesktopDrop({
      files: [
        {
          name: "a.txt",
          url: "http://127.0.0.1:1/drop/token/0",
          type: "text/plain",
          size: 5,
        },
      ],
    });

    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe("a.txt");
    expect(files[0]?.type).toBe("text/plain");
  });

  it("returns nothing when the payload has no files", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(filesFromDesktopDrop({ files: [] })).resolves.toEqual([]);
    await expect(filesFromDesktopDrop(undefined)).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
