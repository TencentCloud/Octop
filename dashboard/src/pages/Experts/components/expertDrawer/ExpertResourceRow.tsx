import type { CSSProperties, ReactNode } from "react";
import { Button, Dropdown, Tooltip } from "antd";
import { MoreHorizontal } from "lucide-react";

import { useTextOverflow } from "./useTextOverflow";
import styles from "./expertDrawer.module.less";

type RowMenuItem = {
  key: string;
  label: string;
  danger?: boolean;
  onClick?: () => void;
};

/**
 * One row of a resource list (config file / skill / subagent) in the
 * expert drawers: icon + label + secondary line + inline actions.
 *
 * Show up to two actions directly, including the row's own action
 * (e.g. Edit). For three or more, show the first action and More.
 */
export default function ExpertResourceRow({
  icon,
  iconStyle,
  label,
  secondary,
  secondaryIsPath = true,
  hint,
  onOpen,
  menuItems,
  menuLabel,
}: {
  /** Icon node (emoji, meta.icon or img). */
  icon: ReactNode;
  /** Inline color/background for the icon tile. */
  iconStyle?: CSSProperties;
  /** Primary label. */
  label: string;
  /** Secondary line: path (monospace) or description. */
  secondary?: string;
  /** Render secondary with the monospace path style. */
  secondaryIsPath?: boolean;
  /** Inline action hint shown at the right (e.g. "Edit"). */
  hint?: string;
  /** Click on the row body. */
  onOpen?: () => void;
  /** Additional row actions, in display order. */
  menuItems?: RowMenuItem[];
  /** aria-label for the overflow button. */
  menuLabel?: string;
}) {
  const secondaryClass = secondaryIsPath
    ? styles.rowPath
    : styles.rowDescription;
  const { ref: secondaryRef, tooltip } = useTextOverflow<HTMLDivElement>(
    secondary,
    secondaryClass,
  );

  const actions = menuItems ?? [];
  // Unified rule (per review): at most ONE visible action per row — the
  // inline hint (Edit) when present, else the first action. Everything
  // beyond that collapses into the overflow "more" menu.
  const hintCount = hint ? 1 : 0;
  const inlineActions = hint ? [] : actions.slice(0, 1);
  const overflowActions = actions.slice(Math.max(0, 1 - hintCount));

  return (
    <div className={styles.row}>
      <Tooltip title={tooltip} trigger={["hover", "focus"]}>
        <button
          type="button"
          className={styles.rowMain}
          onClick={onOpen}
          disabled={!onOpen}
          style={onOpen ? undefined : { cursor: "default" }}
        >
          <div className={styles.rowIcon} style={iconStyle}>
            {icon}
          </div>
          <div className={styles.rowMeta}>
            <div className={styles.rowLabel}>{label}</div>
            {secondary ? (
              <div ref={secondaryRef} className={secondaryClass}>
                {secondary}
              </div>
            ) : null}
          </div>
          {hint ? <span className={styles.rowHint}>{hint}</span> : null}
        </button>
      </Tooltip>
      {inlineActions.length > 0 ? (
        <div
          className={
            inlineActions.length === 1
              ? styles.rowActionsSingle
              : styles.rowActions
          }
        >
          {inlineActions.map((item) => (
            <Button
              key={item.key}
              type="link"
              size="small"
              danger={item.danger}
              className={styles.rowActionButton}
              onClick={(e) => {
                e.stopPropagation();
                item.onClick?.();
              }}
            >
              {item.label}
            </Button>
          ))}
        </div>
      ) : null}
      {overflowActions.length > 0 ? (
        <Dropdown menu={{ items: overflowActions }} trigger={["click"]}>
          <button
            type="button"
            className={styles.rowMenu}
            aria-label={menuLabel}
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal size={16} />
          </button>
        </Dropdown>
      ) : null}
    </div>
  );
}
