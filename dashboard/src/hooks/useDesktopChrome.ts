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
import { getDesktopBridge, isDesktopShell } from "../utils/desktopBridge";

const DesktopChromeContext = createContext<DesktopChromeStyle | null>(null);

/**
 * Activate desktop window chrome when the Electron preload bridge is present.
 * macOS traffic lights and the Windows/Linux caption overlay sit on the page,
 * so this publishes how much space they need. Dragging stays pure CSS
 * (`app-region`), no JS listeners needed.
 */
export function useDesktopChrome(): DesktopChromeStyle | null {
  const [style, setStyle] = useState<DesktopChromeStyle | null>(null);

  useEffect(() => {
    if (!isDesktopShell()) return;
    const next = resolveDesktopChromeStyle();
    let fullscreen = false;
    const publish = () =>
      applyDesktopChrome(next, document.documentElement, fullscreen);
    publish();
    setStyle(next);
    // Fullscreen removes the native buttons. Drop the inset so the menu row
    // and the page stop reserving their strip.
    const unsubscribe = getDesktopBridge()?.onWindowFullscreenChange?.(
      (value) => {
        fullscreen = value;
        publish();
      },
    );
    return () => unsubscribe?.();
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
