import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSessionWorkIds } from "./useSessionWorkIds";
import type { StreamEvent } from "./chatStore";

let listener: ((event: StreamEvent) => void) | null = null;

vi.mock("./chatStore", () => ({
  onStreamEvent: (fn: (event: StreamEvent) => void) => {
    listener = fn;
    return () => {
      listener = null;
    };
  },
}));

describe("useSessionWorkIds", () => {
  afterEach(() => {
    listener = null;
  });

  it("tracks stream start and end for a thread", () => {
    const { result } = renderHook(() => useSessionWorkIds());
    expect(result.current.has("thr_1")).toBe(false);

    act(() => {
      listener?.({ kind: "streamStart", sessionId: "thr_1" });
    });
    expect(result.current.has("thr_1")).toBe(true);

    act(() => {
      listener?.({ kind: "streamResume", sessionId: "thr_1" });
    });
    expect(result.current.has("thr_1")).toBe(true);

    act(() => {
      listener?.({ kind: "streamEnd", sessionId: "thr_1" });
    });
    expect(result.current.has("thr_1")).toBe(false);
  });
});
