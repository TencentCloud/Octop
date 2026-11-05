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
 * macOS traffic lights and the Windows caption overlay sit on the page, so
 * this publishes how much space they need. Dragging stays pure CSS
 * (`app-region`), no JS listeners needed.
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
