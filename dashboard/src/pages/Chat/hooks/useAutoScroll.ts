/**
 * useAutoScroll — streaming chat scroll state machine.
 *
 * Two mutually exclusive scroll modes (stored in scrollModeRef):
 *
 *  "follow" — default. New content scrolls to the bottom automatically.
 *  "free"   — user scrolled up intentionally. No automatic movement.
 *             ↓ button is shown. Restored to "follow" when user reaches bottom.
 *
 * Programmatic scroll guard:
 *  Any scrollTo / scrollIntoView fires scroll events. We mark them as
 *  programmatic via isProgrammaticScrollRef so handleScroll ignores them.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { VirtuosoHandle } from "react-virtuoso";
import { shouldEnterFreeModeOnScrollUp } from "./scrollFreeMode";

// ─── constants ────────────────────────────────────────────────────────────────

/** px from bottom — counts as "at the bottom" for sticky follow / overscroll */
export const AT_BOTTOM_THRESHOLD = 80;

/**
 * Resume follow (and hide ↓) only when truly near the end.
 * Using AT_BOTTOM_THRESHOLD here immediately undid free mode after a small
 * scroll-up inside the sticky zone, so the jump-to-bottom control never stayed.
 */
export const FOLLOW_RESUME_THRESHOLD = 12;

/** ms to keep the programmatic-scroll guard alive (covers smooth-scroll animation) */
const PROGRAMMATIC_GUARD_MS = 700;

/** Instant follow after streaming layout — longer than one paint on Safari. */
const INSTANT_FOLLOW_GUARD_MS = 320;

/** ms to wait after touchend before re-checking (iOS momentum settle) */
const MOMENTUM_SETTLE_MS = 200;

/** px before a touch gesture counts as intentional scroll-up */
const TOUCH_SCROLL_UP_THRESHOLD = 10;

/** Accumulated overscroll at bottom before firing refresh */
export const OVERSCROLL_BOTTOM_THRESHOLD = 80;

// ─── types ────────────────────────────────────────────────────────────────────

type ScrollMode = "follow" | "free";

export interface VirtualScrollConfig {
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  scrollerRef: React.RefObject<HTMLElement | null>;
  /** Latest item count; prefer ref so listener effects need not rebind. */
  itemCountRef: React.RefObject<number>;
  /** Virtuoso absolute-index base when using firstItemIndex prepend anchoring. */
  firstItemIndexRef?: React.RefObject<number>;
}

export interface UseAutoScrollOptions {
  deps?: readonly unknown[];
  smooth?: boolean;
  containerRef?: React.RefObject<HTMLElement | null>;
  endRef?: React.RefObject<HTMLElement | null>;
  virtual?: VirtualScrollConfig | null;
  /** Bumps when the Virtuoso scroller element mounts so listeners re-bind. */
  scrollerMountKey?: number;
  onNearTop?: () => void;
  nearTopThreshold?: number;
  /**
   * Optional override for "at top" (Virtuoso + firstItemIndex: scrollTop is not
   * near 0 when the first item is visible). When omitted, uses scrollTop.
   */
  isAtTop?: () => boolean;
  /** Fired when the user keeps scrolling down while already at the bottom. */
  onOverscrollBottom?: () => void;
  overscrollBottomThreshold?: number;
  /** When true on a deps tick, skip the automatic instant follow scroll. */
  skipNextDepsScrollRef?: React.MutableRefObject<boolean>;
}

export interface UseAutoScrollReturn {
  containerRef: React.RefObject<HTMLDivElement>;
  endRef: React.RefObject<HTMLDivElement>;
  showScrollBtn: boolean;
  isFollowMode: boolean;
  /**
   * @param instant Jump without smooth animation.
   * @param sync When true with instant, pin in the current turn (use from
   *   useLayoutEffect so the new bubble is visible before paint).
   */
  scrollToBottom: (instant?: boolean, sync?: boolean) => void;
  resumeAutoScroll: () => void;
  armProgrammaticGuard: (ms?: number) => void;
  handleAtBottomChange: (bottom: boolean) => void;
}

// ─── hook ─────────────────────────────────────────────────────────────────────

export function useAutoScroll({
  deps = [],
  smooth = true,
  containerRef: externalContainerRef,
  endRef: externalEndRef,
  virtual = null,
  scrollerMountKey = 0,
  onNearTop,
  nearTopThreshold = AT_BOTTOM_THRESHOLD,
  isAtTop,
  onOverscrollBottom,
  overscrollBottomThreshold = OVERSCROLL_BOTTOM_THRESHOLD,
  skipNextDepsScrollRef,
}: UseAutoScrollOptions = {}): UseAutoScrollReturn {
  const internalContainerRef = useRef<HTMLDivElement>(null);
  const internalEndRef = useRef<HTMLDivElement>(null);
  const containerRef = externalContainerRef ?? internalContainerRef;
  const endRef = externalEndRef ?? internalEndRef;

  const scrollModeRef = useRef<ScrollMode>("follow");
  const rafRef = useRef<number | null>(null);
  const isProgrammaticRef = useRef(false);
  const guardTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Overscroll-to-refresh state kept in refs so it survives listener effect
  // re-mounts (e.g. when onOverscrollBottom identity changes mid-refresh).
  const overscrollAccumRef = useRef(0);
  const overscrollArmedRef = useRef(true);
  /** True while the user is wheel/touch-scrolling past the bottom (refresh). */
  const bottomOverscrollIntentRef = useRef(false);
  const prevScrollTopRef = useRef(0);

  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [isFollowMode, setIsFollowMode] = useState(true);

  const virtualRef = useRef(virtual);
  virtualRef.current = virtual;

  const getScroller = useCallback((): HTMLElement | null => {
    if (virtualRef.current?.scrollerRef.current) {
      return virtualRef.current.scrollerRef.current;
    }
    return containerRef.current;
  }, [containerRef]);

  const armProgrammaticGuard = useCallback(
    (ms = PROGRAMMATIC_GUARD_MS) => {
      isProgrammaticRef.current = true;
      if (guardTimerRef.current !== null) clearTimeout(guardTimerRef.current);
      guardTimerRef.current = setTimeout(() => {
        guardTimerRef.current = null;
        isProgrammaticRef.current = false;
        const scroller = getScroller();
        if (scroller) {
          prevScrollTopRef.current = scroller.scrollTop;
        }
      }, ms);
    },
    [getScroller],
  );

  const isAtBottom = useCallback(
    (threshold = AT_BOTTOM_THRESHOLD): boolean => {
      const c = getScroller();
      if (!c) return true;
      return c.scrollHeight - c.scrollTop - c.clientHeight <= threshold;
    },
    [getScroller],
  );

  const enterFollowMode = useCallback(() => {
    scrollModeRef.current = "follow";
    setIsFollowMode(true);
    setShowScrollBtn(false);
  }, []);

  const enterFreeMode = useCallback(() => {
    scrollModeRef.current = "free";
    setIsFollowMode(false);
    setShowScrollBtn(true);
    isProgrammaticRef.current = false;
    if (guardTimerRef.current !== null) {
      clearTimeout(guardTimerRef.current);
      guardTimerRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const pinScrollerToBottom = useCallback(
    (scroller: HTMLElement, instant: boolean) => {
      armProgrammaticGuard(
        instant ? INSTANT_FOLLOW_GUARD_MS : PROGRAMMATIC_GUARD_MS,
      );
      if (instant) {
        // Always assign — skipping when gap===0 missed Virtuoso/tool rows whose
        // scrollHeight catches up a frame later, leaving the user one notch up.
        scroller.scrollTop = scroller.scrollHeight;
      } else {
        scroller.scrollTo({
          top: scroller.scrollHeight,
          behavior: "smooth",
        });
      }
      prevScrollTopRef.current = scroller.scrollTop;
    },
    [armProgrammaticGuard],
  );

  const scrollToBottomInFollowMode = useCallback(
    (instant = false, sync = false) => {
      if (scrollModeRef.current !== "follow") return;

      const run = () => {
        if (scrollModeRef.current !== "follow") return;

        const v = virtualRef.current;
        const itemCount = v?.itemCountRef.current ?? 0;
        if (v && itemCount > 0) {
          const scroller = v.scrollerRef.current;
          if (scroller) {
            pinScrollerToBottom(scroller, instant);
          } else {
            armProgrammaticGuard(
              instant ? INSTANT_FOLLOW_GUARD_MS : PROGRAMMATIC_GUARD_MS,
            );
            const firstIdx = v.firstItemIndexRef?.current ?? 0;
            v.virtuosoRef.current?.scrollToIndex({
              index: firstIdx + itemCount - 1,
              align: "end",
              behavior: instant ? "auto" : "smooth",
            });
          }
          return;
        }

        const scroller = getScroller();
        if (instant && scroller) {
          pinScrollerToBottom(scroller, instant);
          return;
        }

        const end = endRef.current;
        if (!end) return;
        armProgrammaticGuard(PROGRAMMATIC_GUARD_MS);
        end.scrollIntoView({
          behavior: instant || !smooth ? "instant" : "smooth",
          block: "end",
        });
      };

      // Sync path: pin before paint (send / streaming follow). Skip rAF coalesce.
      if (sync && instant) {
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
        run();
        return;
      }

      // Non-sync: one rAF so layout/Virtuoso can settle. (Double rAF lagged
      // streaming follow by ~2 frames so the last bubble felt like it "popped".)
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        run();
      });
    },
    [smooth, armProgrammaticGuard, pinScrollerToBottom, endRef, getScroller],
  );

  const scrollToBottom = useCallback(
    (instant = false, sync = false) => {
      enterFollowMode();
      scrollToBottomInFollowMode(instant, sync);
    },
    [enterFollowMode, scrollToBottomInFollowMode],
  );

  const resumeAutoScroll = useCallback(() => {
    scrollToBottom(smooth);
  }, [scrollToBottom, smooth]);

  const handleAtBottomChange = useCallback(() => {
    // Virtuoso may report at-bottom after programmatic follow scrolls.
    // Resuming follow is handled only by user scroll/wheel/touch listeners.
  }, []);

  // Layout-phase follow: pin before paint so growing bubbles never sit below
  // the fold for a frame. One trailing rAF re-pins after Virtuoso/tool measure.
  useLayoutEffect(() => {
    if (skipNextDepsScrollRef?.current) {
      skipNextDepsScrollRef.current = false;
      return;
    }
    if (scrollModeRef.current !== "follow") return;

    scrollToBottomInFollowMode(true, true);

    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      if (scrollModeRef.current === "follow") {
        scrollToBottomInFollowMode(true, true);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies dynamic dependency list
  }, [...deps, scrollToBottomInFollowMode, skipNextDepsScrollRef]);

  useEffect(() => {
    const container = getScroller();
    if (!container) return;

    prevScrollTopRef.current = container.scrollTop;

    const checkAtTop = (): boolean => {
      if (isAtTop) return isAtTop();
      return container.scrollTop <= nearTopThreshold;
    };

    // Disarmed after one refresh; only re-armed once the user genuinely
    // leaves the bottom and returns, so a single flick's momentum can't fire
    // the refresh twice.
    const resetOverscroll = () => {
      overscrollAccumRef.current = 0;
      overscrollArmedRef.current = true;
      bottomOverscrollIntentRef.current = false;
    };

    const accumulateOverscroll = (delta: number) => {
      if (!onOverscrollBottom || !overscrollArmedRef.current || !isAtBottom()) {
        return;
      }
      if (delta <= 0) {
        overscrollAccumRef.current = Math.max(
          0,
          overscrollAccumRef.current + delta,
        );
        return;
      }
      bottomOverscrollIntentRef.current = true;
      overscrollAccumRef.current += delta;
      if (overscrollAccumRef.current >= overscrollBottomThreshold) {
        overscrollAccumRef.current = 0;
        overscrollArmedRef.current = false;
        bottomOverscrollIntentRef.current = false;
        onOverscrollBottom();
      }
    };

    const handleScroll = (): void => {
      const cur = container.scrollTop;
      const prev = prevScrollTopRef.current;
      prevScrollTopRef.current = cur;

      const upDelta = prev - cur;
      const scrolledUp = upDelta > 1;

      // Rubber-band at the bottom while pulling past the end must not clear
      // overscroll intent or yank into free mode.
      const bottomPullNoise =
        bottomOverscrollIntentRef.current && isAtBottom() && scrolledUp;

      // Under the programmatic pin guard, ignore scrollTop dips — Virtuoso and
      // layout often emit them right after pinScrollerToBottom. User intent to
      // leave follow is handled by wheel/touch (which clear the guard).
      if (
        !isProgrammaticRef.current &&
        !bottomPullNoise &&
        scrolledUp &&
        shouldEnterFreeModeOnScrollUp({
          upDelta,
          atBottom: isAtBottom(),
        })
      ) {
        resetOverscroll();
        enterFreeMode();
      }

      // Load earlier messages whenever we're near the top.
      if (
        onNearTop &&
        checkAtTop() &&
        (scrollModeRef.current === "free" || !isProgrammaticRef.current)
      ) {
        onNearTop();
      }

      if (isProgrammaticRef.current) return;

      if (scrolledUp) {
        if (!bottomPullNoise) resetOverscroll();
        return;
      }

      // Scrolling down / settled: only resume follow when truly near the end.
      if (isAtBottom(FOLLOW_RESUME_THRESHOLD)) {
        enterFollowMode();
      } else if (scrollModeRef.current === "free") {
        setShowScrollBtn(true);
        resetOverscroll();
      } else {
        resetOverscroll();
      }
    };

    const handleWheel = (e: WheelEvent): void => {
      if (e.deltaY < 0) {
        resetOverscroll();
        enterFreeMode();
        // Already at top: scrollTop will not move — still load earlier.
        if (onNearTop && checkAtTop()) {
          onNearTop();
        }
        return;
      }
      // Bottom overscroll refresh must work even under programmatic pin.
      if (e.deltaY > 0 && isAtBottom()) {
        if (!isProgrammaticRef.current && isAtBottom(FOLLOW_RESUME_THRESHOLD)) {
          enterFollowMode();
        }
        accumulateOverscroll(e.deltaY);
        return;
      }
      if (isProgrammaticRef.current) return;
    };

    let touchStartY = 0;
    let touchLastY = 0;

    const handleTouchStart = (e: TouchEvent): void => {
      touchStartY = e.touches[0]?.clientY ?? 0;
      touchLastY = touchStartY;
    };

    const handleTouchMove = (e: TouchEvent): void => {
      const y = e.touches[0]?.clientY ?? 0;
      const dyFromStart = y - touchStartY;
      const dyStep = touchLastY - y; // positive when finger moves up
      touchLastY = y;
      if (dyFromStart > TOUCH_SCROLL_UP_THRESHOLD) {
        resetOverscroll();
        enterFreeMode();
        // Finger pulls down at top → load earlier (scrollTop may already be 0).
        if (onNearTop && checkAtTop()) {
          onNearTop();
        }
        return;
      }
      // Finger moves up → content scrolls down; when already at bottom, count
      // as overscroll toward refresh.
      if (dyStep > 0 && isAtBottom()) {
        accumulateOverscroll(dyStep);
      }
    };

    const handleTouchEnd = (): void => {
      setTimeout(() => {
        if (isAtBottom(FOLLOW_RESUME_THRESHOLD)) {
          enterFollowMode();
        } else if (scrollModeRef.current === "free") {
          setShowScrollBtn(true);
          resetOverscroll();
        } else {
          resetOverscroll();
        }
      }, MOMENTUM_SETTLE_MS);
    };

    const handleResize = (): void => {
      if (scrollModeRef.current === "follow") {
        // Sync pin — RO already fires after layout; another double-rAF lag
        // is what made streaming follow feel late.
        scrollToBottomInFollowMode(true, true);
        return;
      }
      // Free mode: never hide ↓ from resize/layout. Only enterFollowMode does.
      setShowScrollBtn(true);
    };

    const ro = new ResizeObserver(handleResize);
    const observeScrollerChildren = () => {
      for (const child of Array.from(container.children)) {
        if (child instanceof HTMLElement) {
          ro.observe(child);
        }
      }
    };
    ro.observe(container);
    // Streaming thinking/tools grow inside content children; the scroller
    // box itself often does not resize. Observe every direct child — and
    // re-observe when Virtuoso inserts Header/Footer later.
    observeScrollerChildren();
    const mo = new MutationObserver(observeScrollerChildren);
    mo.observe(container, { childList: true });

    container.addEventListener("scroll", handleScroll, { passive: true });
    container.addEventListener("wheel", handleWheel, { passive: true });
    container.addEventListener("touchstart", handleTouchStart, {
      passive: true,
    });
    container.addEventListener("touchmove", handleTouchMove, { passive: true });
    container.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      mo.disconnect();
      ro.disconnect();
      container.removeEventListener("scroll", handleScroll);
      container.removeEventListener("wheel", handleWheel);
      container.removeEventListener("touchstart", handleTouchStart);
      container.removeEventListener("touchmove", handleTouchMove);
      container.removeEventListener("touchend", handleTouchEnd);
      if (guardTimerRef.current !== null) clearTimeout(guardTimerRef.current);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [
    getScroller,
    scrollToBottomInFollowMode,
    isAtBottom,
    enterFollowMode,
    enterFreeMode,
    onNearTop,
    nearTopThreshold,
    isAtTop,
    onOverscrollBottom,
    overscrollBottomThreshold,
    scrollerMountKey,
  ]);

  return {
    containerRef: internalContainerRef,
    endRef: internalEndRef,
    showScrollBtn,
    isFollowMode,
    scrollToBottom,
    resumeAutoScroll,
    armProgrammaticGuard,
    handleAtBottomChange,
  };
}
