export type DesktopShortcutAction =
  | "show_desktop"
  | "open_terminal"
  | "open_menu"
  | "open_files"
  | "close_window";

/** Ask the server to run a host desktop shortcut (launch app / key combo). */
export function sendDesktopAction(
  sendEvent: (event: Record<string, unknown>) => boolean,
  action: DesktopShortcutAction,
): boolean {
  return sendEvent({ type: "desktop_action", action });
}
