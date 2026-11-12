import { Tabs } from "antd";
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
}

/** Underline tab bar. Overflow uses Ant Design Tabs' own more menu. */
export default function TabBar<T extends string>({
  tabs,
  activeKey,
  onChange,
}: TabBarProps<T>) {
  const { t } = useTranslation();

  return (
    <Tabs
      className={styles.tabBar}
      activeKey={activeKey}
      onChange={(key) => onChange(key as T)}
      items={tabs.map((tab) => ({
        key: tab.key,
        label: <TabLabel icon={tab.icon}>{t(tab.labelKey)}</TabLabel>,
      }))}
    />
  );
}
