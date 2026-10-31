import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import styles from "./RailEdgeControl.module.less";

interface RailEdgeControlProps {
  /** Whether the panel this edge belongs to is currently expanded. */
  expanded: boolean;
  onToggle: () => void;
  /**
   * ``end`` — edge sits on the right of an expanded panel (collapse btn to the left).
   * ``start`` — edge sits where a collapsed panel was (expand btn to the right).
   */
  side?: "end" | "start";
  /** Optional aria / tooltip label override. */
  label?: string;
  /**
   * Optional tooltip text when it should differ from the accessible name —
   * e.g. the same action plus its keyboard accelerator.
   */
  hint?: string;
  /** Keyboard accelerator, published to AT only. */
  shortcut?: string;
  className?: string;
  /**
   * When false, keep the hover hit-target / button but do not paint a divider
   * (used when this edge shares a line with a neighboring rail).
   */
  showLine?: boolean;
  /**
   * Two handles can land on the same seam (the history rail, when collapsed,
   * sits on the nav rail's own divider). Overlapping there is unreadable, so
   * they stack: one above the centre, one below.
   */
  stack?: "none" | "top" | "bottom";
  /**
   * Paint the button at rest instead of only on hover. Use it when the panel is
   * collapsed: the header that normally carries the control is gone, so a
   * hover-only pill would be the panel's only way back and nobody would find it.
   */
  persistent?: boolean;
}

/**
 * Collapse/expand handle anchored to a vertical rail seam.
 *
 * Both left columns fold from one of these: a capsule straddling the divider,
 * centred on it, quiet at rest and crisp under the pointer. It replaced the
 * pair of `PanelLeft*` glyphs that used to sit in each rail's own header —
 * same action, one shape, and the handle is attached to the line that moves.
 */
export default function RailEdgeControl({
  expanded,
  onToggle,
  side = "end",
  label,
  hint,
  shortcut,
  className,
  showLine = true,
  stack = "none",
  persistent = false,
}: RailEdgeControlProps) {
  const { t } = useTranslation();
  const ariaLabel =
    label ??
    (expanded
      ? t("layout.collapsePanel", "收起面板")
      : t("layout.expandPanel", "展开面板"));

  return (
    <div
      className={cx(
        styles.edge,
        side === "start" ? styles.edgeStart : styles.edgeEnd,
        expanded ? styles.edgeExpanded : styles.edgeCollapsed,
        className,
      )}
    >
      {showLine ? <div className={styles.line} aria-hidden /> : null}
      <button
        type="button"
        className={cx(
          styles.btn,
          stack === "top" && styles.btnTop,
          stack === "bottom" && styles.btnBottom,
          persistent && styles.btnPersistent,
        )}
        onClick={onToggle}
        aria-label={ariaLabel}
        aria-expanded={expanded}
        aria-keyshortcuts={shortcut}
        title={hint ?? ariaLabel}
      >
        {expanded ? (
          <ChevronLeft size={15} strokeWidth={2} aria-hidden />
        ) : (
          <ChevronRight size={15} strokeWidth={2} aria-hidden />
        )}
      </button>
    </div>
  );
}
