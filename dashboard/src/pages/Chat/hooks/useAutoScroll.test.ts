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
  const maxTop = () => Math.max(0, el.scrollHeight - el.clientHeight);
  let top = Math.min(maxTop(), Math.max(0, scrollTop));
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
      top = Math.min(maxTop(), Math.max(0, value));
    },
    configurable: true,
  });
  el.scrollTo = vi.fn(({ top: nextTop }: ScrollToOptions) => {
    top = Math.min(maxTop(), Math.max(0, nextTop ?? top));
  }) as unknown as typeof el.scrollTo;
  return el;
}

/**
 * Replace the no-op ResizeObserver stub (from src/test/setup.ts) with one we
 * can fire manually, mirroring the real browser delivering RO callbacks after
 * the dock resizes the scroller.
 */
function installCallableResizeObserver() {
  const instances: Array<{ emit: () => void }> = [];
  class MockResizeObserver {
    private readonly cb: ResizeObserverCallback;
    constructor(cb: ResizeObserverCallback) {
      this.cb = cb;
      instances.push(this);
    }
    observe() {}
    unobserve() {}
    disconnect() {}
    emit() {
      this.cb([], this as unknown as ResizeObserver);
    }
  }
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  return instances;
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

  it("re-binds listeners when scrollerMountKey bumps after late container attach", () => {
    // Mirrors MessageList: first paint is a loading spinner (no scroller), then
    // the list mounts and bumps scrollerMountKey so wheel/scroll work.
    const containerRef: { current: HTMLElement | null } = { current: null };
    const end = document.createElement("div");
    end.scrollIntoView = vi.fn();
    const endRef = { current: end };

    const { result, rerender } = renderHook(
      ({ mountKey }: { mountKey: number }) =>
        useAutoScroll({
          containerRef,
          endRef,
          deps: [],
          scrollerMountKey: mountKey,
        }),
      { initialProps: { mountKey: 0 } },
    );

    const container = makeScroller();
    containerRef.current = container;
    rerender({ mountKey: 1 });

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
    expect(container.scrollTop).toBe(800);
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

    // Mount/follow scroll arms INSTANT_FOLLOW_GUARD_MS (320).
    act(() => {
      vi.advanceTimersByTime(400);
    });

    act(() => {
      container.scrollTop = 500;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.showScrollBtn).toBe(true);
    expect(result.current.isFollowMode).toBe(false);
    vi.useRealTimers();
  });

  it("does not leave follow mode on tiny near-bottom dips (Safari reflow)", () => {
    vi.useFakeTimers();
    // Mount pins to max scrollTop (800). A 2px upward nudge is noise.
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
      vi.advanceTimersByTime(400);
    });

    act(() => {
      container.scrollTop = 798;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.showScrollBtn).toBe(false);
    expect(result.current.isFollowMode).toBe(true);
    vi.useRealTimers();
  });

  it("leaves follow mode on intentional upward scroll even near the bottom", () => {
    vi.useFakeTimers();
    // 20px up from max (800→780) while still within the 80px sticky zone.
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
      vi.advanceTimersByTime(400);
    });

    act(() => {
      container.scrollTop = 780;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.showScrollBtn).toBe(true);
    expect(result.current.isFollowMode).toBe(false);
    vi.useRealTimers();
  });

  it("does not show the jump-to-bottom control after a layout clamp at the bottom", () => {
    // Regression: closing the file dock grows the viewport, so the browser
    // clamps scrollTop to the new max and fires a fake "scroll-up". The user
    // never scrolled — the ↓ control must not appear and mode stays follow.
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

    act(() => {
      vi.advanceTimersByTime(400);
    });

    // Dock closes → max scrollTop drops from 800 to 600; the browser rewrites
    // scrollTop to 600 (the setter clamps it).
    Object.defineProperty(container, "scrollHeight", {
      value: 800,
      configurable: true,
    });
    act(() => {
      container.scrollTop = 800;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);
    vi.useRealTimers();
  });

  it("stays at the bottom with no button through a dock open/close resize cycle", () => {
    // Regression (real browser, not just the stub): opening the file dock
    // shrinks the chat scroller, closing it grows it back. The browser then
    // clamps scrollTop and fires a fake "scroll-up" plus a ResizeObserver
    // callback. Neither may surface the ↓ control while the user is at the
    // bottom.
    vi.useFakeTimers();
    const roInstances = installCallableResizeObserver();
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
      vi.advanceTimersByTime(400);
    });
    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);

    // Dock opens → scroller shrinks 200 → 120; follow pins to new max 880.
    Object.defineProperty(container, "clientHeight", {
      value: 120,
      configurable: true,
    });
    act(() => {
      roInstances.forEach((ro) => ro.emit());
    });
    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);
    expect(container.scrollTop).toBe(880);

    act(() => {
      vi.advanceTimersByTime(400);
    });

    // Dock closes → scroller grows 120 → 200; max drops 880 → 800, so the
    // browser clamps scrollTop to 800 (the setter clamps it).
    Object.defineProperty(container, "clientHeight", {
      value: 200,
      configurable: true,
    });
    act(() => {
      container.scrollTop = 880;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    act(() => {
      roInstances.forEach((ro) => ro.emit());
    });

    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);
    vi.useRealTimers();
  });

  it("drops a stale jump-to-bottom control when a layout clamp lands at the bottom in free mode", () => {
    // The user was already in free mode (scrolled up earlier), then a layout
    // change clamps them back to the bottom. The ↓ control must disappear even
    // though no scroll-down event fires to trigger the normal resume path.
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

    act(() => {
      vi.advanceTimersByTime(400);
    });

    // User scrolls up genuinely → free mode, button shown.
    act(() => {
      container.scrollTop = 750;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    expect(result.current.isFollowMode).toBe(false);
    expect(result.current.showScrollBtn).toBe(true);

    // Content shrinks (scrollHeight 1000 → 850): the browser clamps scrollTop
    // from 750 to the new max 650 — a scroll-up event whose resulting position
    // is exactly the bottom. Follow must resume and the button must hide, even
    // though no scroll-down event fires the normal resume path.
    Object.defineProperty(container, "scrollHeight", {
      value: 850,
      configurable: true,
    });
    act(() => {
      container.scrollTop = 750; // setter clamps to 650
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);
    vi.useRealTimers();
  });

  it("keeps the jump-to-bottom control after scrolling up inside the sticky zone", () => {
    vi.useFakeTimers();
    // Regression: resume-follow used the loose 80px threshold, so a settle
    // scroll while still "at bottom" immediately hid ↓ again.
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
      vi.advanceTimersByTime(400);
    });

    act(() => {
      container.scrollTop = 760;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    expect(result.current.isFollowMode).toBe(false);
    expect(result.current.showScrollBtn).toBe(true);

    // A non-upward settle while still in the sticky zone must not cancel free.
    act(() => {
      container.scrollTop = 762;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    expect(result.current.isFollowMode).toBe(false);
    expect(result.current.showScrollBtn).toBe(true);
    vi.useRealTimers();
  });

  it("does not leave follow mode on scroll-up noise under programmatic pin", () => {
    // Virtuoso/layout often emits scrollTop dips right after a pin. Those must
    // not steal follow mode — only wheel/touch may interrupt during the guard.
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
      useAutoScroll({ containerRef, endRef, deps: ["stream"] }),
    );

    expect(result.current.isFollowMode).toBe(true);

    act(() => {
      container.scrollTop = 760;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    expect(result.current.isFollowMode).toBe(true);
    expect(result.current.showScrollBtn).toBe(false);
    vi.useRealTimers();
  });

  it("enters free mode on wheel up even under programmatic pin guard", () => {
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
      useAutoScroll({ containerRef, endRef, deps: ["stream"] }),
    );

    expect(result.current.isFollowMode).toBe(true);

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40, bubbles: true }),
      );
    });

    expect(result.current.isFollowMode).toBe(false);
    expect(result.current.showScrollBtn).toBe(true);
    vi.useRealTimers();
  });

  it("pins on deps change in layout without waiting for rAF", () => {
    // Streaming follow must not lag two frames behind content growth.
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);

    const container = makeScroller({
      scrollHeight: 1200,
      clientHeight: 200,
      scrollTop: 700,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { rerender } = renderHook(
      ({ token }: { token: number }) =>
        useAutoScroll({ containerRef, endRef, deps: [token] }),
      { initialProps: { token: 1 } },
    );

    Object.defineProperty(container, "scrollHeight", {
      value: 1400,
      configurable: true,
    });

    act(() => {
      rerender({ token: 2 });
    });

    expect(container.scrollTop).toBe(1200);
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

    expect(container.scrollTop).toBe(1000);
    expect(endRef.current.scrollIntoView).not.toHaveBeenCalled();
  });

  it("sync instant scroll pins without waiting for rAF", () => {
    // Deferred rAF never runs — sync path must still pin (send / layout).
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);

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
      result.current.scrollToBottom(true, true);
    });

    expect(container.scrollTop).toBe(1000);
  });

  it("still assigns scrollTop on instant pin when already at the bottom", () => {
    // Rewriting scrollTop when gap===0 is intentional: Virtuoso/tool growth
    // often reports gap 0 before scrollHeight catches up.
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
      result.current.scrollToBottom(true);
    });

    expect(container.scrollTop).toBe(800);
  });

  it("loads earlier messages when wheeling up while already at the top", () => {
    // At scrollTop===0 further wheel-up does not change scrollTop, so scroll
    // near-top alone never fires — must treat top overscroll as load-older.
    const onNearTop = vi.fn();
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 0,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    renderHook(() =>
      useAutoScroll({ containerRef, endRef, deps: [], onNearTop }),
    );

    act(() => {
      // Mount follow-pin may have moved scrollTop to the bottom — restore top.
      container.scrollTop = 0;
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40, bubbles: true }),
      );
    });

    expect(onNearTop).toHaveBeenCalled();
  });

  it("loads earlier via isAtTop when Virtuoso scrollTop is not near zero", () => {
    const onNearTop = vi.fn();
    const container = makeScroller({
      scrollHeight: 50000,
      clientHeight: 200,
      scrollTop: 12000,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    renderHook(() =>
      useAutoScroll({
        containerRef,
        endRef,
        deps: [],
        onNearTop,
        isAtTop: () => true,
      }),
    );

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -30, bubbles: true }),
      );
    });

    expect(onNearTop).toHaveBeenCalled();
  });

  it("fires bottom overscroll refresh under programmatic pin guard", () => {
    vi.useFakeTimers();
    const onOverscrollBottom = vi.fn();
    const container = makeScroller({
      scrollHeight: 1000,
      clientHeight: 200,
      scrollTop: 800,
    });
    const containerRef = { current: container };
    const endRef = { current: document.createElement("div") };
    endRef.current.scrollIntoView = vi.fn();

    const { result } = renderHook(() =>
      useAutoScroll({
        containerRef,
        endRef,
        deps: ["stream"],
        onOverscrollBottom,
        overscrollBottomThreshold: 50,
      }),
    );

    // Mount/deps pin arms the programmatic guard — do not wait it out.
    expect(result.current.isFollowMode).toBe(true);

    act(() => {
      container.dispatchEvent(
        new WheelEvent("wheel", { deltaY: 60, bubbles: true }),
      );
    });

    expect(onOverscrollBottom).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
