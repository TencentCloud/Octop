import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { request } from "../../../api/request";
import { useWorkspaceFileMention } from "./useWorkspaceFileMention";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

describe("useWorkspaceFileMention", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(request).mockReset();
  });

  it("does not glob on empty or one-character queries", () => {
    const { rerender } = renderHook(
      ({ query }) => useWorkspaceFileMention("A1", true, query),
      { initialProps: { query: "" } },
    );
    expect(request).not.toHaveBeenCalled();
    rerender({ query: "s" });
    expect(request).not.toHaveBeenCalled();
  });

  it("aborts the in-flight glob when the query changes", async () => {
    vi.useFakeTimers();
    let rejectFirst: ((err: Error) => void) | undefined;
    vi.mocked(request)
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectFirst = reject;
          }),
      )
      .mockResolvedValueOnce([{ path: "docs/api.md" }]);

    const { rerender, result } = renderHook(
      ({ query }) => useWorkspaceFileMention("A1", true, query),
      { initialProps: { query: "ap" } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(request).toHaveBeenCalledTimes(1);

    rerender({ query: "api" });
    expect(rejectFirst).toBeTypeOf("function");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(request).toHaveBeenCalledTimes(2);
    expect(result.current.files.map((file) => file.path)).toEqual([
      "docs/api.md",
    ]);
  });
});
