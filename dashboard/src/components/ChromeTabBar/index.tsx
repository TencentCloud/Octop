import { useCallback, useRef } from "react";
import type { KeyboardEvent, MouseEvent, ReactNode } from "react";
import { Tooltip } from "antd";
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const onTabKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>) => {
      const idx = tabs.findIndex((tab) => tab.key === activeKey);
      let next = -1;
      if (event.key === "ArrowRight") next = (idx + 1) % tabs.length;
      else if (event.key === "ArrowLeft")
        next = (idx - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      const target = tabs[next];
      if (!target) return;
      onChange(target.key);
      tabRefs.current.get(target.key)?.focus();
    },
    [tabs, activeKey, onChange],
  );

  return (
    <div className={[styles.tabBar, className].filter(Boolean).join(" ")}>
      <div className={styles.tabsScroll} role="tablist">
        {tabs.map((tab) => {
          const selected = tab.key === activeKey;
          const node = (
            <button
              type="button"
              role="tab"
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              ref={(el) => {
                if (el) tabRefs.current.set(tab.key, el);
                else tabRefs.current.delete(tab.key);
              }}
              onKeyDown={onTabKeyDown}
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
                  aria-label={t("common.close")}
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
            </button>
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
