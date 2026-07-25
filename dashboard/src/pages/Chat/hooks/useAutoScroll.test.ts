import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAutoScroll } from "./useAutoScroll";

function makeScroller({
  scrollHeight = 1000,
  clientHeight = 200,
  scrollTop = 700,
}: {
  scrollHeight?: number;
  clientHeight?: number;
  scrollTop?: number;
} = {}) {
  const el = document.createElement("div");
  let top = scrollTop;
  Object.defineProperty(el, "scrollHeight", {
    value: scrollHeight,
    configurable: true,
  });
  Object.defineProperty(el, "clientHeight", {
    value: clientHeight,
    configurable: true,
  });
  Object.defineProperty(el, "scrollTop", {
    get: () => top,
    set: (value: number) => {
      top = value;
    },
    configurable: true,
  });
  el.scrollTo = vi.fn(({ top: nextTop }: ScrollToOptions) => {
    top = nextTop ?? top;
  }) as unknown as typeof el.scrollTo;
  return el;
}

describe("useAutoScroll", () => {
  beforeEach(() => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 1;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("enters free mode on wheel up and shows the scroll button", () => {
    const container = makeScroller();
    const containerRef = { current: container };
    const end = document.createElement("div");
    end.scrollIntoView = vi.fn();
    const endRef = { current: end };

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40, bubbles: true }),
      );
    });

    expect(result.current.showScrollBtn).toBe(true);
  });

  it("does not follow new deps while in free mode", () => {
    const container = makeScroller();
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result, rerender } = renderHook(
      ({ token }: { token: number }) =>
        useAutoScroll({ containerRef, endRef, deps: [token] }),
      { initialProps: { token: 1 } },
    );

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40, bubbles: true }),
      );
    });
    expect(result.current.showScrollBtn).toBe(true);

    endRef.current.scrollIntoView = vi.fn();
    rerender({ token: 2 });

    expect(endRef.current.scrollIntoView).not.toHaveBeenCalled();
  });

  it("resumes follow mode when scrollToBottom is called", () => {
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 400,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40, bubbles: true }),
      );
    });
    expect(result.current.showScrollBtn).toBe(true);

    act(() => {
      result.current.scrollToBottom(true);
    });

    expect(result.current.showScrollBtn).toBe(false);
    expect(container.scrollTop).toBe(1000);
  });

  it("enters free mode when scroll moves clearly away from the bottom", () => {
    vi.useFakeTimers();
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 800,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    // Mount/follow scroll arms a short programmatic guard — expire it first.
    act(() => {
      vi.advanceTimersByTime(250);
    });

    act(() => {
      container.scrollTop = 500;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.showScrollBtn).toBe(true);
    expect(result.current.isFollowMode).toBe(false);
    vi.useRealTimers();
  });

  it("does not leave follow mode when scrollTop dips but still near bottom", () => {
    vi.useFakeTimers();
    // At bottom: scrollHeight 1000, client 200 → bottom starts at 800.
    // A 20px upward nudge (780) is still within AT_BOTTOM_THRESHOLD (80).
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 800,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    act(() => {
      vi.advanceTimersByTime(250);
    });

    act(() => {
      container.scrollTop = 780;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.showScrollBtn).toBe(false);
    expect(result.current.isFollowMode).toBe(true);
    vi.useRealTimers();
  });

  it("pins with scrollTop assignment on instant follow scrolls", () => {
    const container = makeScroller({
      scrollHeight: 1200,
      clientHeight: 200,
      scrollTop: 700,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    act(() => {
      result.current.scrollToBottom(true);
    });

    expect(container.scrollTop).toBe(1200);
    expect(endRef.current.scrollIntoView).not.toHaveBeenCalled();
  });

  it("skips instant pin when already exactly at the bottom", () => {
    // gap === 0 → should not rewrite scrollTop.
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 800,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [] }),
    );

    const before = container.scrollTop;
    act(() => {
      result.current.scrollToBottom(true);
    });

    expect(container.scrollTop).toBe(before);
  });
});
