/**
 * Keyboard contract for the two left rails.
 *
 *   mod+B        → nav rail (the one with the logo, far left)
 *   mod+shift+B  → conversation-history rail (nested beside the nav on chat)
 *
 * mod is ⌘ on macOS and Ctrl elsewhere. `B` is what editors and IDEs already
 * put in people's fingers for "toggle the sidebar"; the history rail borrows
 * the same key with Shift instead of inventing a second letter, so the pair
 * reads as one feature rather than two.
 *
 * Everything here is pure so the matching rules can be tested without a DOM.
 */

export type RailShortcutAction = "toggle-nav" | "toggle-history";

/** The subset of KeyboardEvent the matcher needs. */
export interface RailShortcutEvent {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

/**
 * Map a keydown to the rail it toggles, or `null` when the event is not ours.
 *
 * Deliberately strict: a bare `B` never matches, and Alt is excluded because
 * `⌥B` / `Alt+B` are word-motion and menu accelerators on the platforms we
 * ship to. Shift picks the second rail rather than a different key.
 */
export function matchRailShortcut(
  event: RailShortcutEvent,
): RailShortcutAction | null {
  if (event.altKey) return null;
  if (!event.metaKey && !event.ctrlKey) return null;
  if (event.key.toLowerCase() !== "b") return null;
  return event.shiftKey ? "toggle-history" : "toggle-nav";
}

/**
 * Whether the event should be left alone for someone else to handle.
 *
 * Two cases matter:
 *  - A dialog is open: `mod+B` inside a modal belongs to the modal's world (and
 *    Escape/most accelerators are its business), so the rails stay put.
 *  - The caret is in a rich-text surface: contenteditable owns `mod+B` for
 *    bold. Plain inputs and textareas do *not* own it — the composers are
 *    plain textareas, and people expect the sidebar shortcut to work while
 *    typing, the way it does in an editor.
 */
export function shouldIgnoreRailShortcut(
  target: EventTarget | null,
  hasOpenDialog: boolean,
): boolean {
  if (hasOpenDialog) return true;
  const element = target as
    | (EventTarget & { isContentEditable?: boolean })
    | null;
  return Boolean(element?.isContentEditable);
}

/**
 * True while an IME is composing. A native counterpart of `utils/ime`, which
 * takes React's synthetic event; the rails listen on `window` directly.
 */
export function isComposingKeyEvent(event: {
  isComposing?: boolean;
  keyCode?: number;
}): boolean {
  return Boolean(event.isComposing) || event.keyCode === 229;
}

/** Human-readable accelerator for tooltips and `aria-keyshortcuts`. */
export function railShortcutLabel(
  action: RailShortcutAction,
  isMac: boolean,
): string {
  if (isMac) return action === "toggle-nav" ? "⌘B" : "⇧⌘B";
  return action === "toggle-nav" ? "Ctrl+B" : "Ctrl+Shift+B";
}

/** Value for `aria-keyshortcuts` (the spec wants "Meta+B", not "⌘B"). */
export function railShortcutAria(action: RailShortcutAction): string {
  return action === "toggle-nav" ? "Meta+B" : "Meta+Shift+B";
}

export function isMacPlatform(userAgent = navigator.userAgent): boolean {
  return /Mac|iPhone|iPad/.test(userAgent);
}
