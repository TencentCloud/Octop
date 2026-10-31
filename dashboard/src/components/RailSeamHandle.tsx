import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./RailSeamHandle.module.less";

/**
 * Vertical distance between the two handles when their seams coincide.
 *
 * With three columns there are two seams. Collapse the history rail and its
 * seam lands on the nav's — the handles would sit on top of each other. They
 * are pushed apart by half this (one up, one down) so the pair reads as a
 * stack, and the asymmetry is only a few dozen pixels when the two seams are
 * apart anyway.
 */
export const SEAM_HANDLE_STEP = 34;

interface RailSeamHandleProps {
  /** Whether the panel to the left of this seam is currently open. */
  open: boolean;
  onToggle: () => void;
  /** Accessible name — the action ("收起导航栏"), never the state. */
  label?: string;
  /** Tooltip when it carries more than the name (e.g. its accelerator). */
  hint?: string;
  /** Keyboard accelerator, published to AT only. */
  shortcut?: string;
  /**
   * Nudge off the seam's vertical centre, in px. Negative sits the handle
   * above the centre line, positive below.
   */
  offsetY?: number;
  /**
   * Paint the handle at rest. Used while its panel is collapsed: the header
   * that used to carry a control is gone, so a hover-only pill would be the
   * only way back and nobody would find it.
   */
  persistent?: boolean;
  className?: string;
}

/**
 * Fold control anchored to a vertical seam between two columns.
 *
 * It is not part of either column's content: the host column is relative and
 * the capsule straddles its trailing border at `left: 100%`, so folding the
 * column drags the handle along with the line it belongs to — the arrow then
 * flips (◀ to fold, ▶ to reopen) and the handle ends up on the new edge
 * without any second placement rule. Quiet at rest, crisp under the pointer;
 * the 8px either side of the seam that it spans is its hit area.
 */
export default function RailSeamHandle({
  open,
  onToggle,
  label,
  hint,
  shortcut,
  offsetY = 0,
  persistent = false,
  className,
}: RailSeamHandleProps) {
  const { t } = useTranslation();
  const name =
    label ??
    (open
      ? t("layout.collapsePanel", "收起面板")
      : t("layout.expandPanel", "展开面板"));

  return (
    <div
      className={[
        styles.anchor,
        persistent ? styles.persistent : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ "--seam-offset": `${offsetY}px` } as React.CSSProperties}
    >
      <button
        type="button"
        className={styles.btn}
        onClick={onToggle}
        aria-label={name}
        aria-expanded={open}
        aria-keyshortcuts={shortcut}
        title={hint ?? name}
        data-seam-handle
      >
        {open ? (
          <ChevronLeft size={14} strokeWidth={2.2} aria-hidden />
        ) : (
          <ChevronRight size={14} strokeWidth={2.2} aria-hidden />
        )}
      </button>
    </div>
  );
}
