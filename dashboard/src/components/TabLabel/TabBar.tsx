import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import TabLabel from "./index";
import styles from "./index.module.less";

export interface TabBarItem<T extends string = string> {
  key: T;
  labelKey: string;
  icon: LucideIcon;
}

interface TabBarProps<T extends string> {
  tabs: readonly TabBarItem<T>[];
  activeKey: T;
  onChange: (key: T) => void;
}

/** Shared underline tab bar with Lucide icons (admin advanced style). */
export default function TabBar<T extends string>({
  tabs,
  activeKey,
  onChange,
}: TabBarProps<T>) {
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
            <TabLabel icon={tab.icon}>{t(tab.labelKey)}</TabLabel>
          </button>
        );
      })}
    </div>
  );
}
