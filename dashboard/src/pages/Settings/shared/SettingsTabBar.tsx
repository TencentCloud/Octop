import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import styles from "../AdvancedSettings/index.module.less";

export interface SettingsTabItem<T extends string = string> {
  key: T;
  labelKey: string;
  icon?: ReactNode;
}

interface SettingsTabBarProps<T extends string> {
  tabs: SettingsTabItem<T>[];
  activeKey: T;
  onChange: (key: T) => void;
}

/** Shared underline tab bar for admin settings pages (Security / Advanced / Plugins). */
export default function SettingsTabBar<T extends string>({
  tabs,
  activeKey,
  onChange,
}: SettingsTabBarProps<T>) {
  const { t } = useTranslation();

  return (
    <div className={styles.tabBar} role="tablist">
      {tabs.map((tab) => {
        const selected = activeKey === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={selected}
            className={`${styles.tab} ${selected ? styles.active : ""}`}
            onClick={() => onChange(tab.key)}
          >
            {tab.icon ? (
              <span className={styles.tabIcon} aria-hidden="true">
                {tab.icon}
              </span>
            ) : null}
            {t(tab.labelKey)}
          </button>
        );
      })}
    </div>
  );
}
