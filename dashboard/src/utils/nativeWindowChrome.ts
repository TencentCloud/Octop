import { loadAppearanceOnBoot, type ThemePreference } from "../styles/appearanceStorage";
import { getDesktopBridge, isDesktopShell } from "./desktopBridge";

/**
 * Push the page theme to the shell so its *native* window buttons match.
 *
 * The shell keeps the OS-drawn controls (macOS traffic lights, Windows caption
 * buttons); they follow `nativeTheme`, not our CSS variables, so a dark
 * Dashboard would otherwise sit under black glyphs. `scheme` is the user's
 * preference, which keeps "follow the system" tracking the OS rather than
 * pinning whatever we resolved today. No-op in the browser (server mode).
 */
export function applyNativeWindowChrome(
  mode: "light" | "dark",
  scheme: ThemePreference,
): void {
  if (!isDesktopShell()) return;
  // Optional call: a shell from before this handshake has no such method.
  getDesktopBridge()?.setWindowChrome?.({ mode, scheme });
}

/**
 * The same handshake, run once from the boot module before React mounts.
 *
 * The window becomes visible around first paint, so waiting for an effect would
 * show the native glyphs in the wrong colour for a frame. Reading the stored
 * preference here means the shell is correct before anything is on screen; the
 * hook then only has to keep it in sync.
 */
export function bootNativeWindowChrome(
  prefersDark: boolean = window.matchMedia("(prefers-color-scheme: dark)")
    .matches,
): void {
  if (!isDesktopShell()) return;
  const { preference } = loadAppearanceOnBoot();
  const mode =
    preference === "system" ? (prefersDark ? "dark" : "light") : preference;
  applyNativeWindowChrome(mode, preference);
}
