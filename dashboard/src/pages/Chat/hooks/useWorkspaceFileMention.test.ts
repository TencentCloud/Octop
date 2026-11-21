import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { request } from "../../../api/request";
import { clearWorkspaceMentionIndexCache } from "../utils/fileMention";
import { useWorkspaceFileMention } from "./useWorkspaceFileMention";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

describe("useWorkspaceFileMention", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(request).mockReset();
    clearWorkspaceMentionIndexCache();
  });

  it("loads the file index once and filters later keystrokes locally", async () => {
    vi.mocked(request).mockResolvedValue({
      paths: ["docs/api.md", "docs/guide.md", "notes/soul.md"],
    });

    const { result, rerender } = renderHook(
      ({ query }) => useWorkspaceFileMention("A1", true, query),
      { initialProps: { query: "" } },
    );

    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(request).mock.calls[0]?.[0])).toContain(
      "/workspace/mention-index",
    );
    expect(result.current.files).toEqual([]);

    rerender({ query: "a" });
    expect(result.current.files).toEqual([]);
    expect(request).toHaveBeenCalledTimes(1);

    rerender({ query: "ap" });
    expect(result.current.files.map((file) => file.path)).toEqual([
      "docs/api.md",
    ]);
    expect(request).toHaveBeenCalledTimes(1);

    rerender({ query: "docs/api" });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
    });
    expect(request).toHaveBeenCalledTimes(1);
    expect(result.current.truncated).toBe(false);
  });

  it("does not request an index when no agent is selected", async () => {
    const { result, rerender } = renderHook(
      ({ query }) => useWorkspaceFileMention(null, true, query),
      { initialProps: { query: "" } },
    );
    await act(async () => {});
    expect(request).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();

    rerender({ query: "so" });
    expect(result.current.error).toBe("need_agent");
  });

  it("globs a path-shaped query only when the index is truncated", async () => {
    vi.useFakeTimers();
    vi.mocked(request)
      .mockResolvedValueOnce({
        paths: ["notes/a.md"],
        truncated: true,
      })
      .mockResolvedValueOnce([{ path: "docs/api.md" }]);

    const { result, rerender } = renderHook(
      ({ query }) => useWorkspaceFileMention("A1", true, query),
      { initialProps: { query: "so" } },
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(request).toHaveBeenCalledTimes(1);
    expect(result.current.truncated).toBe(true);
    expect(result.current.files).toEqual([]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(request).toHaveBeenCalledTimes(1);

    rerender({ query: "docs/api" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(request).toHaveBeenCalledTimes(2);
    expect(String(vi.mocked(request).mock.calls[1]?.[0])).toContain(
      "/workspace/glob",
    );
    expect(String(vi.mocked(request).mock.calls[1]?.[0])).toContain(
      "from_workspace=true",
    );
    expect(result.current.files.map((file) => file.path)).toEqual([
      "docs/api.md",
    ]);
    expect(result.current.truncated).toBe(true);
  });
});
