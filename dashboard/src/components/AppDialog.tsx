import { useCallback, useEffect, useRef } from "react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export type AppDialogProps = {
  open: boolean;
  onClose: () => void;
  /** Accessible name for the dialog surface. */
  ariaLabel: string;
  /** `dialog` for informational sheets, `alertdialog` for interrupting ones. */
  role?: "dialog" | "alertdialog";
  /** Dismiss on Escape and on overlay clicks. Alert dialogs may opt out. */
  dismissable?: boolean;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
};

/**
 * Minimal modal-dialog contract shared by the hand-rolled overlays that
 * declare `aria-modal` (audit A11Y-5): moves focus in on open, traps
 * Tab/Shift+Tab inside the subtree, closes on Escape, and restores focus to
 * the trigger on unmount.
 */
export function AppDialog({
  open,
  onClose,
  ariaLabel,
  role = "dialog",
  dismissable = true,
  children,
  className,
  style,
}: AppDialogProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement;
    const container = containerRef.current;
    const first = container?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? container)?.focus();
    return () => {
      const prev = restoreFocusRef.current;
      if (prev instanceof HTMLElement && document.contains(prev)) {
        prev.focus();
      }
    };
  }, [open]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (dismissable && event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const container = containerRef.current;
      if (!container) return;
      const focusables = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => el.offsetParent !== null || el === container);
      if (focusables.length === 0) {
        event.preventDefault();
        return;
      }
      const firstEl = focusables[0];
      const lastEl = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === firstEl || !container.contains(active)) {
          event.preventDefault();
          lastEl.focus();
        }
      } else if (active === lastEl || !container.contains(active)) {
        event.preventDefault();
        firstEl.focus();
      }
    },
    [dismissable, onClose],
  );

  if (!open) return null;

  return createPortal(
    <div
      className={className}
      style={style}
      onClick={
        dismissable
          ? (e) => e.target === e.currentTarget && onClose()
          : undefined
      }
    >
      <div
        ref={containerRef}
        role={role}
        aria-modal="true"
        aria-label={ariaLabel}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        style={{ outline: "none" }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
