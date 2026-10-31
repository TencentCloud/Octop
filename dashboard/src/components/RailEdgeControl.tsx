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
  className?: string;
  /**
   * When false, keep the hover hit-target / button but do not paint a divider
   * (used when this edge shares a line with a neighboring rail).
   */
  showLine?: boolean;
  /**
   * ``center`` straddles the divider (folder-tree toggle).
   * ``before`` / ``after`` sit on either side when two rails share one line.
   */
  placement?: "center" | "before" | "after";
  /**
   * Paint the button at rest instead of only on hover. Use it when the panel is
   * collapsed: the header that normally carries the control is gone, so a
   * hover-only pill would be the panel's only way back and nobody would find it.
   */
  persistent?: boolean;
}

/**
 * Collapse/expand control anchored to a vertical rail line.
 * Matches the knowledge-base folder tree edge button.
 */
export default function RailEdgeControl({
  expanded,
  onToggle,
  side = "end",
  label,
  hint,
  className,
  showLine = true,
  placement = "center",
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
        !expanded && styles.edgeCollapsed,
        className,
      )}
    >
      {showLine ? <div className={styles.line} aria-hidden /> : null}
      <button
        type="button"
        className={cx(
          styles.btn,
          placement === "before" && styles.btnBefore,
          placement === "after" && styles.btnAfter,
          persistent && styles.btnPersistent,
        )}
        onClick={onToggle}
        aria-label={ariaLabel}
        title={hint ?? ariaLabel}
      >
        {expanded ? (
          <ChevronLeft size={14} strokeWidth={2} aria-hidden />
        ) : (
          <ChevronRight size={14} strokeWidth={2} aria-hidden />
        )}
      </button>
    </div>
  );
}
