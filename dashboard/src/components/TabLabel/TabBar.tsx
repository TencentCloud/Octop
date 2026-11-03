import { useTranslation } from "react-i18next";
import TabLabel, { type TabIcon } from "./index";
import styles from "./index.module.less";

export interface TabBarItem<T extends string = string> {
  key: T;
  labelKey: string;
  icon: TabIcon;
}

interface TabBarProps<T extends string> {
  tabs: readonly TabBarItem<T>[];
  activeKey: T;
  onChange: (key: T) => void;
  /**
   * Plain text tabs (no icons) matching the Experts-page antd Tabs look:
   * secondary text, near-black selected text, black underline.
   */
  plain?: boolean;
}

/** Shared underline tab bar (admin advanced style). */
export default function TabBar<T extends string>({
  tabs,
  activeKey,
  onChange,
  plain = false,
}: TabBarProps<T>) {
  const { t } = useTranslation();

  if (plain) {
    return (
      <div className={styles.tabBarPlain} role="tablist">
        {tabs.map((tab) => {
          const selected = activeKey === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={selected}
              className={`${styles.tabPlain} ${selected ? styles.active : ""}`}
              onClick={() => onChange(tab.key)}
            >
              {t(tab.labelKey)}
            </button>
          );
        })}
      </div>
    );
  }

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
