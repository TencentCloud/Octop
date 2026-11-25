import { useEffect } from "react";

import { useTheme } from "../context/ThemeContext";
import { applyNativeWindowChrome } from "../utils/nativeWindowChrome";

/**
 * Keep the shell's native window buttons in the app's theme as the user changes
 * it. The first (pre-paint) report comes from `bootNativeWindowChrome()` in the
 * boot module; this effect only handles later changes.
 */
export function useNativeWindowChrome(): void {
  const { isDark, preference } = useTheme();

  useEffect(() => {
    applyNativeWindowChrome(isDark ? "dark" : "light", preference);
  }, [isDark, preference]);
}
