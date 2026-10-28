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
 * Activate desktop window chrome when the Electron preload bridge is present.
 * The shell keeps the native buttons (macOS traffic lights, Windows caption
 * buttons), so this only publishes how much space they need; dragging stays
 * pure CSS (`app-region`), no JS listeners needed.
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
