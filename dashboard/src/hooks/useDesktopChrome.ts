import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  applyDesktopChrome,
  injectedDesktopChromeStyle,
  installDesktopWindowDrag,
  isDesktopShell,
  resolveDesktopChromeStyle,
  type DesktopChromeStyle,
} from "../utils/desktopChrome";

const DesktopChromeContext = createContext<DesktopChromeStyle | null>(null);

/** Activate frameless window chrome after the Wails bridge appears. */
export function useDesktopChrome(): DesktopChromeStyle | null {
  const [style, setStyle] = useState<DesktopChromeStyle | null>(null);

  useEffect(() => {
    let cancelled = false;
    let recheck = 0;
    const applyNow = () => {
      const next = resolveDesktopChromeStyle();
      applyDesktopChrome(next);
      setStyle(next);
      if (injectedDesktopChromeStyle()) return;
      // First paint can race the Go injection; re-resolve once it lands.
      recheck = window.setTimeout(() => {
        if (cancelled) return;
        const again = resolveDesktopChromeStyle();
        applyDesktopChrome(again);
        setStyle(again);
      }, 1200);
    };
    const tryApply = () => {
      if (cancelled || !isDesktopShell()) return false;
      applyNow();
      installDesktopWindowDrag();
      return true;
    };
    if (tryApply()) {
      return () => {
        cancelled = true;
        window.clearTimeout(recheck);
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
      window.clearTimeout(recheck);
    };
  }, []);

  return style;
}

export function DesktopChromeProvider({
  value,
  children,
}: {
  value: DesktopChromeStyle | null;
  children: ReactNode;
}) {
  return createElement(DesktopChromeContext.Provider, { value }, children);
}

export function useDesktopChromeStyle(): DesktopChromeStyle | null {
  return useContext(DesktopChromeContext);
}
