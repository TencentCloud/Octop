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
    const container = makeScroller({ scrollTop: 400 });
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
    expect(endRef.current.scrollIntoView).toHaveBeenCalled();
  });
});
