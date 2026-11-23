import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

import styles from "./expertDrawer.module.less";

/**
 * Collapsible block for the expert drawers. Children stay mounted while
 * hidden (display: none) so a save without expanding still submits field
 * values and defaults (conversation mode, model, trajectory, runtime
 * params, custom id…). Replaces MoreConfigCollapse.
 */
export default function ExpertDrawerCollapsible({
  title,
  defaultOpen = false,
  prominent = false,
  children,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  prominent?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={styles.collapsible}>
      <button
        type="button"
        className={
          prominent
            ? styles.collapsibleProminentToggle
            : styles.collapsibleToggle
        }
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={styles.collapsibleTitle}>{title}</span>
        <span
          className={
            open
              ? `${styles.collapsibleIcon} ${styles.collapsibleIconOpen}`
              : styles.collapsibleIcon
          }
        >
          <ChevronDown size={14} aria-hidden />
        </span>
      </button>
      <div style={open ? undefined : { display: "none" }}>{children}</div>
    </div>
  );
}
