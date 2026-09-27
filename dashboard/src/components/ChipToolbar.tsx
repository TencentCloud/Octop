import type { ReactNode } from "react";
import { Popover, Tooltip } from "antd";
import styles from "./ChipToolbar.module.less";

/**
 * Chip toolbar + chip button (PLAN §9 contract).
 *
 * Mirrors the "Tooltip wrapping a button, optionally wrapped in a
 * click-triggered Popover" pattern used by the chat composer, but is a
 * standalone project-domain component: it must never import the chat page's
 * private modules (S-11), and it owns no business requests.
 *
 * ``disabled`` renders ``aria-disabled`` and short-circuits ``onClick``
 * instead of using the native attribute or ``pointer-events: none`` — the chip
 * stays focusable and testable.
 */

export interface ChipToolbarProps {
  /** A series of ``<ChipButton>``. */
  children: ReactNode;
  className?: string;
  testId?: string;
}

export interface ChipButtonProps {
  /** Suggest a lucide icon at size 14. */
  icon: ReactNode;
  /** Already-localized text — the caller passes ``t("projects.…")``. */
  label: string;
  /** Selected-value summary; when non-empty the chip shows ``label：value``. */
  value?: string | null;
  /** Selected highlight. */
  active?: boolean;
  /** Greyed out, still focusable via ``aria-disabled``. */
  disabled?: boolean;
  /** Required for accessibility. */
  ariaLabel: string;
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  /** Popover content; when present the chip opens a click-triggered Popover. */
  children?: ReactNode;
  placement?: "top" | "topLeft" | "bottomLeft";
}

export function ChipToolbar({
  children,
  className,
  testId = "project-chip-toolbar",
}: ChipToolbarProps): JSX.Element {
  return (
    <div
      className={`${styles.toolbar} ${className ?? ""}`.trim()}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

export function ChipButton({
  icon,
  label,
  value,
  active = false,
  disabled = false,
  ariaLabel,
  onClick,
  children,
  placement = "topLeft",
}: ChipButtonProps): JSX.Element {
  const summary = value == null ? "" : String(value).trim();
  const text = summary ? `${label}：${summary}` : label;
  const className = [
    styles.chip,
    active ? styles.chipActive : "",
    disabled ? styles.chipDisabled : "",
  ]
    .filter(Boolean)
    .join(" ");

  const button = (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
      onClick={(e) => {
        if (disabled) return;
        onClick?.(e);
      }}
    >
      <span className={styles.chipIcon} aria-hidden>
        {icon}
      </span>
      <span className={styles.chipLabel}>{text}</span>
    </button>
  );

  const withTooltip = (
    <Tooltip title={ariaLabel} mouseEnterDelay={0.4}>
      {button}
    </Tooltip>
  );

  if (!children || disabled) return withTooltip;

  return (
    <Popover trigger="click" placement={placement} content={children}>
      {withTooltip}
    </Popover>
  );
}

export default ChipToolbar;
