import type { PointerEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
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
  /** Tooltip when it carries more than the name (e.g. its accelerator). */
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
   * ``center`` straddles the divider (folder-tree toggle).
   * ``before`` / ``after`` sit on either side when two rails share one line.
   */
  placement?: "center" | "before" | "after";
  /**
   * Drag the upper stretch of the line to resize the panel. The centered
   * toggle stays a click target.
   */
  onResizeStart?: (event: PointerEvent<HTMLDivElement>) => void;
  resizeLabel?: string;
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
  shortcut,
  className,
  showLine = true,
  placement = "center",
  onResizeStart,
  resizeLabel,
}: RailEdgeControlProps) {
  const { t } = useTranslation();
  const ariaLabel =
    label ??
    (expanded
      ? t("layout.collapsePanel", "收起面板")
      : t("layout.expandPanel", "展开面板"));

  return (
    <div
      className={[
        styles.edge,
        side === "start" ? styles.edgeStart : styles.edgeEnd,
        expanded ? null : styles.edgeCollapsed,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {showLine ? <div className={styles.line} aria-hidden /> : null}
      {onResizeStart ? (
        <div
          className={styles.resizeGrip}
          onPointerDown={onResizeStart}
          role="separator"
          aria-orientation="vertical"
          aria-label={resizeLabel ?? t("chat.resizeSidebar", "调整侧栏宽度")}
        />
      ) : null}
      <button
        type="button"
        className={`${styles.btn} ${
          placement === "before"
            ? styles.btnBefore
            : placement === "after"
            ? styles.btnAfter
            : ""
        }`}
        onClick={onToggle}
        aria-label={ariaLabel}
        aria-expanded={expanded}
        aria-keyshortcuts={shortcut}
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
