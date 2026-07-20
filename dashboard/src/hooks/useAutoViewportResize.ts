import { useEffect, type RefObject } from "react";

interface UseAutoViewportResizeOptions {
  /** Whether auto-resize is active (auto viewport mode / mobile). */
  enabled: boolean;
  /** The visible container whose size drives the browser viewport. */
  containerRef: RefObject<HTMLElement | null>;
  /** Only forward a resize once the stream is live. */
  isStreaming: boolean;
  /** Stream event sender (from useBrowserStream). */
  sendEvent: (event: Record<string, unknown>) => boolean;
  /** Debounce window for resize bursts. */
  debounceMs?: number;
}

/**
 * Keep the browser's viewport aligned with its visible container size.
 *
 * When ``enabled`` (auto viewport mode or mobile), observe container resize and
 * forward ``{ type: "resize" }`` events so Chrome re-renders at the new size
 * instead of being CSS-downscaled. Resize bursts are debounced to avoid
 * flooding the backend.
 *
 * Shared by the chat BrowserWorkspace and the standalone /remote-browser page
 * so the auto-resize behavior lives in exactly one place instead of two
 * near-identical ``ResizeObserver`` blocks.
 */
export function useAutoViewportResize({
  enabled,
  containerRef,
  isStreaming,
  sendEvent,
  debounceMs = 150,
}: UseAutoViewportResizeOptions): void {
  useEffect(() => {
    if (!enabled) return;
    const containerEl = containerRef.current;
    if (!containerEl) return;

    let lastSent = { w: 0, h: 0 };
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;

    const flushResize = () => {
      const w = containerEl.clientWidth;
      const h = containerEl.clientHeight;
      if (w === 0 || h === 0) return;
      if (isStreaming && (w !== lastSent.w || h !== lastSent.h)) {
        lastSent = { w, h };
        sendEvent({ type: "resize", width: w, height: h });
      }
    };

    const onResize = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(flushResize, debounceMs);
    };

    flushResize();
    const ro = new ResizeObserver(onResize);
    ro.observe(containerEl);
    window.addEventListener("resize", onResize);
    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, [enabled, isStreaming, sendEvent, debounceMs, containerRef]);
}
