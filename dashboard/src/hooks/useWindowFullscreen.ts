import { useEffect, useState } from "react";

import { getDesktopBridge } from "../utils/desktopBridge";

/**
 * Whether the shell window is in full screen. Only macOS needs it: the native
 * traffic lights disappear in full screen, so the sidebar has to stop reserving
 * the band that holds them. Always false in the browser, and the app never
 * starts full screen, so there is nothing to seed from the shell at boot.
 */
export function useWindowFullscreen(): boolean {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const unsubscribe = getDesktopBridge()?.onWindowFullscreenChange?.(
      setFullscreen,
    );
    return () => unsubscribe?.();
  }, []);

  return fullscreen;
}
