import { useEffect, useState } from "react";

import { getDesktopBridge } from "../utils/desktopBridge";

/**
 * Whether the shell window is in fullscreen. The layout keeps its shared top
 * row but disables window dragging while fullscreen. Always false in the
 * browser; the shell never starts fullscreen.
 */
export function useWindowFullscreen(): boolean {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const unsubscribe =
      getDesktopBridge()?.onWindowFullscreenChange?.(setFullscreen);
    return () => unsubscribe?.();
  }, []);

  return fullscreen;
}
