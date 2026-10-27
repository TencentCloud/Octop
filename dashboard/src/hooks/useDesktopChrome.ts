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
  resolveDesktopChromeStyle,
  type DesktopChromeStyle,
} from "../utils/desktopChrome";
import { isDesktopShell } from "../utils/desktopBridge";

const DesktopChromeContext = createContext<DesktopChromeStyle | null>(null);

/**
 * Activate frameless window chrome when the Electron preload bridge is present.
 * The preload runs before the first paint, so a single check on mount is enough;
 * window dragging is pure CSS (`-webkit-app-region`), no JS listeners needed.
 */
export function useDesktopChrome(): DesktopChromeStyle | null {
  const [style, setStyle] = useState<DesktopChromeStyle | null>(null);

  useEffect(() => {
    if (!isDesktopShell()) return;
    const next = resolveDesktopChromeStyle();
    applyDesktopChrome(next);
    setStyle(next);
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
