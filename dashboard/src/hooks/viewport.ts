/**
 * Shared mobile / PWA viewport helpers.
 *
 * Two different problems, two fixes:
 * - iOS/Android **PWA**: soft keyboard overlays a `position:fixed; inset:0`
 *   shell → pad the composer with `--keyboard-offset` (see useKeyboardOffset).
 * - **Mobile browser** (esp. Android Chrome): layout viewport stays taller than
 *   the visible area, so the in-flow chat composer is clipped → translate the
 *   composer back into view (see useKeepInVisualViewport). Shrinking `#root`
 *   with visualViewport was tried and did not reliably fix Chrome.
 */

/** Home-indicator / browser chrome is ~34–50px; real keyboards are 200px+. */
export const KEYBOARD_GAP_THRESHOLD_PX = 80;

/** Match dashboard mobile breakpoint (`useIsMobile`). */
export const MOBILE_VIEWPORT_MQ = "(max-width: 767px)";

export function isPwaDisplay(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true;
}

/**
 * Whether the chat composer should self-correct against visualViewport.
 * Narrow viewports, plus Android Chrome "desktop site" (wide layout).
 */
export function needsComposerVisualViewportFix(): boolean {
  if (typeof window === "undefined" || isPwaDisplay()) return false;
  if (window.matchMedia(MOBILE_VIEWPORT_MQ).matches) return true;
  const ua = navigator.userAgent || "";
  return (
    /Android/i.test(ua) &&
    /Chrome|CriOS/i.test(ua) &&
    !/EdgA|OPR|SamsungBrowser|Firefox/i.test(ua)
  );
}

/**
 * Soft-keyboard inset for PWA shells. Tiny leftovers are the home indicator,
 * not a keyboard — leave those at 0 so safe-area padding is not doubled.
 *
 * Prefer `documentElement.clientHeight` over `innerHeight`: on Android Chrome
 * `innerHeight` often already tracks the visual viewport.
 */
export function measureKeyboardOffset(
  layoutHeight: number,
  viewport: Pick<VisualViewport, "height" | "offsetTop">,
): number {
  const raw = Math.max(0, layoutHeight - viewport.height - viewport.offsetTop);
  return raw > KEYBOARD_GAP_THRESHOLD_PX ? Math.round(raw) : 0;
}

export function measureLayoutHeight(): number {
  if (typeof document === "undefined") return 0;
  return Math.max(
    document.documentElement.clientHeight || 0,
    window.innerHeight || 0,
  );
}

export function measureVisualViewportOverflow(
  rectBottom: number,
  viewport: Pick<VisualViewport, "height" | "offsetTop">,
): number {
  return Math.max(0, rectBottom - (viewport.offsetTop + viewport.height));
}
