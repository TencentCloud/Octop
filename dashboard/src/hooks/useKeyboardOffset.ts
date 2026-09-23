import { useEffect } from "react";

/** Home-indicator / browser chrome is ~34–50px; real keyboards are 200px+. */
export const KEYBOARD_GAP_THRESHOLD_PX = 80;

function isPwa(): boolean {
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true;
}

/**
 * VisualViewport leftover after subtracting offsetTop. Tiny gaps are the
 * iOS home indicator, not a keyboard — those must stay 0 or CSS that also
 * adds `env(safe-area-inset-bottom)` will paint two empty bands.
 */
export function measureKeyboardOffset(
  innerHeight: number,
  viewport: Pick<VisualViewport, "height" | "offsetTop">,
): number {
  const raw = Math.max(0, innerHeight - viewport.height - viewport.offsetTop);
  return raw > KEYBOARD_GAP_THRESHOLD_PX ? Math.round(raw) : 0;
}

/**
 * Tracks `--keyboard-offset` on the document root for PWA soft-keyboard layout.
 */
export function useKeyboardOffset() {
  useEffect(() => {
    if (!isPwa()) return;
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      const keyboardHeight = measureKeyboardOffset(window.innerHeight, vv);
      document.documentElement.style.setProperty(
        "--keyboard-offset",
        `${keyboardHeight}px`,
      );
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    update();

    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      document.documentElement.style.removeProperty("--keyboard-offset");
    };
  }, []);
}
