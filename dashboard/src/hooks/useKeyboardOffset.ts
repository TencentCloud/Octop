import { useEffect } from "react";
import {
  isPwaDisplay,
  measureKeyboardOffset,
  measureLayoutHeight,
} from "./viewport";

/**
 * PWA only: keep `inset:0` shell, expose `--keyboard-offset` so the chat
 * composer can clear the soft keyboard (and not the home-indicator twice).
 *
 * Mobile browser clipping is handled by `useKeepInVisualViewport` on the
 * composer — do not also resize `#root` here (ineffective on Android Chrome).
 */
export function useKeyboardOffset() {
  useEffect(() => {
    if (!isPwaDisplay()) return;
    const vv = window.visualViewport;
    if (!vv) return;

    const root = document.documentElement;
    const update = () => {
      const keyboardHeight = measureKeyboardOffset(measureLayoutHeight(), vv);
      root.style.setProperty("--keyboard-offset", `${keyboardHeight}px`);
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    update();

    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      root.style.removeProperty("--keyboard-offset");
    };
  }, []);
}

// Re-export helpers still imported by call sites / tests.
export {
  isPwaDisplay,
  KEYBOARD_GAP_THRESHOLD_PX,
  measureKeyboardOffset,
  measureLayoutHeight,
  needsComposerVisualViewportFix,
} from "./viewport";
