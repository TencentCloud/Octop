import type { ReactNode } from "react";
import { Button, Tooltip } from "antd";

import { QuestionCircleOutlined } from "@ant-design/icons";

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
  tooltip,
  onAction,
}: {
  /** Label text, e.g. "Subagents (1)". */
  label: ReactNode;
  /** Right-side action text, e.g. "Manage subagents". */
  action?: string;
  tooltip?: string;
  onAction?: () => void;
}) {
  return (
    <span className={styles.fieldLabel}>
      <span className={styles.fieldLabelText}>
        {label}
        {tooltip && (
          <Tooltip title={tooltip} trigger={["hover", "focus"]}>
            <button
              type="button"
              className={styles.fieldLabelHelp}
              aria-label={tooltip}
            >
              <QuestionCircleOutlined />
            </button>
          </Tooltip>
        )}
      </span>
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
