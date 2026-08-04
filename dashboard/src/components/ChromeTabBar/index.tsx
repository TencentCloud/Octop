import type { MouseEvent, ReactNode } from "react";
import { Tooltip } from "antd";
import { Plus, X } from "lucide-react";
import styles from "./index.module.less";

export type ChromeTabItem = {
  key: string;
  /** Primary label (text or custom node). Truncated via CSS when long. */
  label: ReactNode;
  /** Optional leading icon / status badge. */
  leading?: ReactNode;
  /** Tooltip on hover (e.g. full URL). */
  tooltip?: ReactNode;
  closable?: boolean;
};

export type ChromeTabBarProps = {
  tabs: ChromeTabItem[];
  activeKey?: string;
  onChange: (key: string) => void;
  onClose?: (key: string, e: MouseEvent) => void;
  onNewTab?: () => void;
  newTabTitle?: string;
  /** Right-side actions (theme, AI panel, …). */
  trailing?: ReactNode;
  className?: string;
};

/**
 * Chrome-style session tab bar shared by the remote browser viewer and
 * terminal workbench so tab chips stay pixel-aligned.
 */
export function ChromeTabBar({
  tabs,
  activeKey,
  onChange,
  onClose,
  onNewTab,
  newTabTitle,
  trailing,
  className,
}: ChromeTabBarProps) {
  return (
    <div className={[styles.tabBar, className].filter(Boolean).join(" ")}>
      <div className={styles.tabsScroll} role="tablist">
        {tabs.map((tab) => {
          const selected = tab.key === activeKey;
          const node = (
            <div
              role="tab"
              aria-selected={selected}
              className={`${styles.tab}${
                selected ? ` ${styles.tabActive}` : ""
              }`}
              onClick={() => onChange(tab.key)}
            >
              {tab.leading}
              <span className={styles.tabLabel}>{tab.label}</span>
              {tab.closable && onClose ? (
                <span
                  className={styles.tabClose}
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    onClose(tab.key, e);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onClose(tab.key, e as unknown as MouseEvent);
                    }
                  }}
                >
                  <X size={10} />
                </span>
              ) : null}
            </div>
          );

          if (tab.tooltip != null && tab.tooltip !== "") {
            return (
              <Tooltip key={tab.key} title={tab.tooltip} mouseEnterDelay={0.8}>
                {node}
              </Tooltip>
            );
          }
          return <span key={tab.key}>{node}</span>;
        })}
        {onNewTab ? (
          <Tooltip title={newTabTitle}>
            <button
              type="button"
              className={styles.tabNew}
              onClick={onNewTab}
              title={newTabTitle}
              aria-label={newTabTitle}
            >
              <Plus size={12} />
            </button>
          </Tooltip>
        ) : null}
      </div>
      {trailing ? <div className={styles.trailing}>{trailing}</div> : null}
    </div>
  );
}
