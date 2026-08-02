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
  className?: string;
  /**
   * When false, keep the hover hit-target / button but do not paint a divider
   * (used when this edge shares a line with a neighboring rail).
   */
  showLine?: boolean;
}

/** Tall, wide-angle chevron (no circular chrome). */
function WideChevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg
      className={styles.chevron}
      viewBox="0 0 10 22"
      width="10"
      height="22"
      aria-hidden
    >
      <path
        d={
          dir === "left"
            ? "M7.5 2.5 L2.5 11 L7.5 19.5"
            : "M2.5 2.5 L7.5 11 L2.5 19.5"
        }
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Hover-revealed collapse/expand control anchored to a vertical rail line.
 */
export default function RailEdgeControl({
  expanded,
  onToggle,
  side = "end",
  label,
  className,
  showLine = true,
}: RailEdgeControlProps) {
  const { t } = useTranslation();
  const ariaLabel =
    label ??
    (expanded
      ? t("layout.collapsePanel", "收起面板")
      : t("layout.expandPanel", "展开面板"));

  return (
    <div
      className={`${styles.edge} ${
        side === "start" ? styles.edgeStart : styles.edgeEnd
      } ${expanded ? styles.edgeExpanded : styles.edgeCollapsed} ${
        className ?? ""
      }`}
    >
      {showLine ? <div className={styles.line} aria-hidden /> : null}
      <button
        type="button"
        className={styles.btn}
        onClick={onToggle}
        aria-label={ariaLabel}
        title={ariaLabel}
      >
        <WideChevron dir={expanded ? "left" : "right"} />
      </button>
    </div>
  );
}
