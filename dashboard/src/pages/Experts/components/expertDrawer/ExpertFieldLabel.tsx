import type { ReactNode } from "react";
import { Button } from "antd";

import styles from "./expertDrawer.module.less";

/**
 * Field-group label row for list sections inside the expert drawers:
 * primary text on the left (matches the antd field-label rule), quiet
 * 12px action link on the right (tertiary, brand on hover). Replaces the
 * previous pattern of reusing the runner-field label style, whose large
 * brand-colored link fought the form-label hierarchy.
 */
export default function ExpertFieldLabel({
  label,
  action,
  onAction,
}: {
  /** Label text, e.g. "Subagents (1)". */
  label: ReactNode;
  /** Right-side action text, e.g. "Manage subagents". */
  action?: string;
  onAction?: () => void;
}) {
  return (
    <span className={styles.fieldLabel}>
      <span className={styles.fieldLabelText}>{label}</span>
      {action && onAction ? (
        <Button
          type="link"
          size="small"
          className={styles.fieldLabelAction}
          onClick={onAction}
        >
          {action}
        </Button>
      ) : null}
    </span>
  );
}
