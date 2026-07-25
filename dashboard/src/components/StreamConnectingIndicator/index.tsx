import type { ReactNode } from "react";
import styles from "./StreamConnectingIndicator.module.less";

const MASCOT_TYPE = `${import.meta.env.BASE_URL}octop-mascot-type.webp`;

interface StreamConnectingIndicatorProps {
  /** Status line under the animation (e.g. 「连接中」). */
  label: ReactNode;
  /** Optional secondary hint. */
  hint?: ReactNode;
}

/**
 * Shared connecting / waiting-frame indicator for remote browser & desktop.
 * Uses the same Octop mascot loop as chat thinking bubbles.
 */
export default function StreamConnectingIndicator({
  label,
  hint,
}: StreamConnectingIndicatorProps) {
  return (
    <div className={styles.root}>
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
