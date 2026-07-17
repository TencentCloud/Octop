import { useCallback, useRef } from "react";
import type { RefObject } from "react";
import type { BrowserViewerHandle } from "../components/BrowserViewer";

/** Concrete (width, height) in CSS pixels. */
export interface ViewportSize {
  width: number;
  height: number;
}

/** Minimal structural shape shared by every surface's tab list. */
export interface StreamTabLike {
  url: string;
  active: boolean;
}

/** Resolve the active tab's URL, ignoring ``about:blank``. Returns "" when
 *  there is no navigable active tab. Shared by the chat panel and the
 *  standalone remote-browser page so both derive the address bar value the
 *  same way. */
export function deriveActiveTabUrl(tabs: StreamTabLike[]): string {
  const active = tabs.find((t) => t.active);
  if (active && active.url && active.url !== "about:blank") return active.url;
  return "";
}

type ConnectStreamFn = (
  url: string,
  width: number,
  height: number,
  callbacks: {
    onFrame: (base64Data: string) => void;
    onStatusChange?: (status: string) => void;
    onError?: (message: string) => void;
  },
  options?: { sessionId?: string | null },
) => void;

interface UseBrowserViewControllerOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  viewerRef: RefObject<BrowserViewerHandle | null>;
  connect: ConnectStreamFn;
  resolveViewport: (
    containerW: number,
    containerH: number,
  ) => ViewportSize | null;
  /** When true, the viewport tracks the container on mobile (fallback
   *  390×700). Desktop surfaces should leave this false. */
  isMobile?: boolean;
  defaultViewport?: ViewportSize;
  onError: (message: string) => void;
  onBeforeConnect?: (sessionId: string) => void;
  onAfterConnect?: (sessionId: string) => void;
}

/**
 * Shared browser-stream controller used by both the chat panel
 * (``BrowserWorkspace``) and the standalone remote-browser page. It owns the
 * only non-trivial glue every surface duplicated: measuring the container,
 * resolving a concrete viewport, opening the WebSocket via ``connect``, and
 * painting incoming frames onto the ``BrowserViewer`` canvas.
 *
 * ``startStream`` is stable across renders (it only re-derives when
 * ``resolveViewport`` changes with the viewport mode), so it is safe to use
 * in effect dependency arrays.
 */
export function useBrowserViewController({
  containerRef,
  viewerRef,
  connect,
  resolveViewport,
  isMobile = false,
  defaultViewport = { width: 1280, height: 800 },
  onError,
  onBeforeConnect,
  onAfterConnect,
}: UseBrowserViewControllerOptions) {
  // Hold the caller-provided callbacks/flags in a ref so ``startStream`` keeps
  // a stable identity even when those inline functions are recreated each
  // render. Only ``resolveViewport`` (which changes with the viewport mode)
  // stays in the dependency list.
  const cfgRef = useRef({
    isMobile,
    defaultViewport,
    onError,
    onBeforeConnect,
    onAfterConnect,
  });
  cfgRef.current = {
    isMobile,
    defaultViewport,
    onError,
    onBeforeConnect,
    onAfterConnect,
  };

  const startStream = useCallback(
    (sessionId: string, targetUrl = "") => {
      const { isMobile: mobile, defaultViewport: fallback, onError: err, onBeforeConnect: before, onAfterConnect: after } =
        cfgRef.current;
      const containerEl = containerRef.current;
      const cw = containerEl?.clientWidth ?? 0;
      const ch = containerEl?.clientHeight ?? 0;

      let size: ViewportSize;
      if (mobile) {
        size =
          cw > 0 && ch > 0
            ? { width: cw, height: ch }
            : { width: 390, height: 700 };
      } else {
        size = resolveViewport(cw, ch) ?? fallback;
      }

      before?.(sessionId);
      connect(
        targetUrl,
        size.width,
        size.height,
        {
          onFrame: (base64Data) => viewerRef.current?.paintFrame(base64Data),
          onError: err,
        },
        { sessionId: sessionId || undefined },
      );
      after?.(sessionId);
    },
    [containerRef, viewerRef, connect, resolveViewport],
  );

  return { startStream };
}
