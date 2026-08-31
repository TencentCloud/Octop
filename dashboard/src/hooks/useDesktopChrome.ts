import { useEffect, useState } from "react";
import {
  applyDesktopChrome,
  installDesktopWindowDrag,
  isDesktopShell,
  resolveDesktopChromeStyle,
  type DesktopChromeStyle,
} from "../utils/desktopChrome";

/** Activate frameless window chrome after the Wails bridge appears. */
export function useDesktopChrome(): DesktopChromeStyle | null {
  const [style, setStyle] = useState<DesktopChromeStyle | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tryApply = () => {
      if (cancelled || !isDesktopShell()) return false;
      const next = resolveDesktopChromeStyle();
      applyDesktopChrome(next);
      installDesktopWindowDrag();
      setStyle(next);
      return true;
    };
    if (tryApply()) {
      return () => {
        cancelled = true;
        applyDesktopChrome(null);
      };
    }
    const timer = window.setInterval(() => {
      if (tryApply()) window.clearInterval(timer);
    }, 250);
    const stop = window.setTimeout(() => window.clearInterval(timer), 12_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.clearTimeout(stop);
      applyDesktopChrome(null);
    };
  }, []);

  return style;
}
