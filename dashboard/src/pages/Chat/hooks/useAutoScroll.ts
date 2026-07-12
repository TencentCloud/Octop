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

import { useCallback, useEffect, useRef, useState } from "react";
import type { VirtuosoHandle } from "react-virtuoso";

// ─── constants ────────────────────────────────────────────────────────────────

/** px from bottom — counts as "at the bottom" */
export const AT_BOTTOM_THRESHOLD = 80;

/** ms to keep the programmatic-scroll guard alive (covers smooth-scroll animation) */
const PROGRAMMATIC_GUARD_MS = 700;

/** ms to wait after touchend before re-checking (iOS momentum settle) */
const MOMENTUM_SETTLE_MS = 200;

/** px before a touch gesture counts as intentional scroll-up */
const TOUCH_SCROLL_UP_THRESHOLD = 10;

// ─── types ────────────────────────────────────────────────────────────────────

type ScrollMode = "follow" | "free";

export interface VirtualScrollConfig {
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  scrollerRef: React.RefObject<HTMLElement | null>;
  itemCount: number;
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
  /** When true on a deps tick, skip the automatic instant follow scroll. */
  skipNextDepsScrollRef?: React.MutableRefObject<boolean>;
}

export interface UseAutoScrollReturn {
  containerRef: React.RefObject<HTMLDivElement>;
  endRef: React.RefObject<HTMLDivElement>;
  showScrollBtn: boolean;
  isFollowMode: boolean;
  scrollToBottom: (instant?: boolean) => void;
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
  const prevScrollTopRef = useRef(0);

  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [isFollowMode, setIsFollowMode] = useState(true);

  const getScroller = useCallback((): HTMLElement | null => {
    if (virtual?.scrollerRef.current) return virtual.scrollerRef.current;
    return containerRef.current;
  }, [virtual, containerRef]);

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

  const isAtBottom = useCallback((): boolean => {
    const c = getScroller();
    if (!c) return true;
    return c.scrollHeight - c.scrollTop - c.clientHeight <= AT_BOTTOM_THRESHOLD;
  }, [getScroller]);

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

  const scrollToBottomInFollowMode = useCallback(
    (instant = false) => {
      if (scrollModeRef.current !== "follow") return;

      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        if (scrollModeRef.current !== "follow") return;

        armProgrammaticGuard(instant ? 50 : PROGRAMMATIC_GUARD_MS);

        if (virtual && virtual.itemCount > 0) {
          const scroller = virtual.scrollerRef.current;
          if (scroller) {
            scroller.scrollTo({
              top: scroller.scrollHeight,
              behavior: instant ? "auto" : "smooth",
            });
          } else {
            virtual.virtuosoRef.current?.scrollToIndex({
              index: virtual.itemCount - 1,
              align: "end",
              behavior: instant ? "auto" : "smooth",
            });
          }
          return;
        }

        const end = endRef.current;
        if (!end) return;
        end.scrollIntoView({
          behavior: instant || !smooth ? "instant" : "smooth",
          block: "end",
        });
      });
    },
    [smooth, armProgrammaticGuard, virtual, endRef],
  );

  const scrollToBottom = useCallback(
    (instant = false) => {
      enterFollowMode();
      scrollToBottomInFollowMode(instant);
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

  useEffect(() => {
    if (skipNextDepsScrollRef?.current) {
      skipNextDepsScrollRef.current = false;
      return;
    }
    if (scrollModeRef.current === "follow") {
      scrollToBottomInFollowMode(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies dynamic dependency list
  }, [...deps, scrollToBottomInFollowMode, skipNextDepsScrollRef]);

  useEffect(() => {
    const container = getScroller();
    if (!container) return;

    prevScrollTopRef.current = container.scrollTop;

    const handleScroll = (): void => {
      const cur = container.scrollTop;
      const prev = prevScrollTopRef.current;
      prevScrollTopRef.current = cur;

      const scrolledUp = cur < prev - 1;

      if (scrolledUp) {
        enterFreeMode();
        return;
      }

      if (isProgrammaticRef.current) return;

      if (isAtBottom()) {
        enterFollowMode();
      }

      if (onNearTop && cur <= nearTopThreshold) {
        onNearTop();
      }
    };

    const handleWheel = (e: WheelEvent): void => {
      if (e.deltaY < 0) {
        enterFreeMode();
        return;
      }
      if (isProgrammaticRef.current) return;
      if (e.deltaY > 0 && isAtBottom()) {
        enterFollowMode();
      }
    };

    let touchStartY = 0;

    const handleTouchStart = (e: TouchEvent): void => {
      touchStartY = e.touches[0]?.clientY ?? 0;
    };

    const handleTouchMove = (e: TouchEvent): void => {
      const dy = (e.touches[0]?.clientY ?? 0) - touchStartY;
      if (dy > TOUCH_SCROLL_UP_THRESHOLD) {
        enterFreeMode();
      }
    };

    const handleTouchEnd = (): void => {
      setTimeout(() => {
        if (isAtBottom()) {
          enterFollowMode();
        }
      }, MOMENTUM_SETTLE_MS);
    };

    const handleResize = (): void => {
      if (scrollModeRef.current === "follow") {
        scrollToBottomInFollowMode(true);
      } else {
        setShowScrollBtn(!isAtBottom());
      }
    };

    const ro = new ResizeObserver(handleResize);
    ro.observe(container);

    container.addEventListener("scroll", handleScroll, { passive: true });
    container.addEventListener("wheel", handleWheel, { passive: true });
    container.addEventListener("touchstart", handleTouchStart, {
      passive: true,
    });
    container.addEventListener("touchmove", handleTouchMove, { passive: true });
    container.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
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
    scrollerMountKey,
    virtual,
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
