import { useEffect, useRef } from "react";

import {
  isComposingKeyEvent,
  matchRailShortcut,
  shouldIgnoreRailShortcut,
} from "../utils/railShortcuts";

const DIALOG_SELECTOR = '[role="dialog"], [role="alertdialog"]';

export interface RailShortcutHandlers {
  onToggleNav: () => void;
  onToggleHistory: () => void;
}

/**
 * Wire ⇧⌘B / ⌘B to the two rails.
 *
 * Bound once on `window` (rails are shell-level, not per page) and kept in a
 * ref so a handler that closes over fresh state — the current route, whether
 * the rail is open — never needs the listener to be re-bound.
 */
export function useRailShortcuts(handlers: RailShortcutHandlers): void {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      if (isComposingKeyEvent(event)) return;
      const action = matchRailShortcut(event);
      if (!action) return;
      const hasOpenDialog = Boolean(document.querySelector(DIALOG_SELECTOR));
      if (shouldIgnoreRailShortcut(event.target, hasOpenDialog)) return;
      event.preventDefault();
      if (action === "toggle-nav") handlersRef.current.onToggleNav();
      else handlersRef.current.onToggleHistory();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
