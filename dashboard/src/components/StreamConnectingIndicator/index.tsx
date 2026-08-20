import type { ReactNode } from "react";
import styles from "./StreamConnectingIndicator.module.less";

const MASCOT_TYPE = `${import.meta.env.BASE_URL}octop-mascot-type.webp`;

interface StreamConnectingIndicatorProps {
  /** Status line under the animation (e.g. 「连接中」). */
  label: ReactNode;
  /** Optional secondary hint. */
  hint?: ReactNode;
  /** Light page chrome vs dark stream surfaces (phone / browser viewport). */
  tone?: "default" | "onDark";
  /** Compact for phone bezel / dock panels. */
  size?: "md" | "sm";
}

/**
 * Shared connecting / waiting-frame indicator for remote browser & desktop.
 * Uses the same Octop mascot loop as chat thinking bubbles.
 */
export default function StreamConnectingIndicator({
  label,
  hint,
  tone = "default",
  size = "md",
}: StreamConnectingIndicatorProps) {
  const rootClass = [
    styles.root,
    tone === "onDark" ? styles.onDark : "",
    size === "sm" ? styles.sizeSm : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
      <img
        className={styles.mascot}
        src={MASCOT_TYPE}
        alt=""
        aria-hidden
        draggable={false}
      />
      <div className={styles.label}>{label}</div>
      {hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
