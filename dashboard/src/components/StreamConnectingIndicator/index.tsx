import type { ReactNode } from "react";
import styles from "./StreamConnectingIndicator.module.less";

const MASCOT_TYPE = `${import.meta.env.BASE_URL}octop-mascot-type.webm`;

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
      <video
        className={styles.mascot}
        src={MASCOT_TYPE}
        autoPlay
        loop
        muted
        playsInline
        aria-hidden
        ref={(el) => {
          if (el) el.muted = true;
        }}
      />
      <div className={styles.label}>{label}</div>
      {hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
