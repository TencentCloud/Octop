import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useElapsedSince } from "./useElapsedSeconds";

describe("useElapsedSince", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts at 0 and advances each second", () => {
    const startedAt = Date.now();
    const { result } = renderHook(() => useElapsedSince(startedAt));

    expect(result.current).toBe(0);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe(1);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current).toBe(3);
  });

  it("resets when startedAt changes", () => {
    const t0 = Date.now();
    const { result, rerender } = renderHook(
      ({ startedAt }) => useElapsedSince(startedAt),
      { initialProps: { startedAt: t0 } },
    );

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe(5);

    const t1 = t0 + 5000;
    rerender({ startedAt: t1 });
    expect(result.current).toBe(0);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current).toBe(2);
  });
});
