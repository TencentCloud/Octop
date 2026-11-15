import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

import styles from "../index.module.less";

/** Centered label with the chevron on its right, same pattern as expert「更多配置」. */
export function AcpSectionToggle({
  label,
  open,
  onToggle,
  children,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className={styles.sectionToggle}>
      <button
        type="button"
        className={styles.sectionToggleButton}
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className={styles.sectionToggleLabel}>
          {label}
          <ChevronDown
            size={14}
            aria-hidden
            className={
              open ? styles.sectionToggleIconOpen : styles.sectionToggleIcon
            }
          />
        </span>
      </button>
      <div style={open ? undefined : { display: "none" }}>{children}</div>
    </div>
  );
}
