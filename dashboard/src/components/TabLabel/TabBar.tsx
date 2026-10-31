import { useTranslation } from "react-i18next";
import TabLabel, { type TabIcon } from "./index";
import styles from "./index.module.less";

/** 底栏单个页签的描述 */
export interface TabBarItem<T extends string = string> {
  /** 页签唯一键，同时写入按钮 data-tab 便于检索 */
  key: T;
  /** i18n 文案键 */
  labelKey: string;
  /** 页签图标 */
  icon: TabIcon;
  /** 文案兜底：传给 i18next 作为 defaultValue，未翻译时仍能显示 */
  fallback?: string;
}

/** 底栏组件属性 */
interface TabBarProps<T extends string> {
  /** 页签列表 */
  tabs: readonly TabBarItem<T>[];
  /** 当前选中键 */
  activeKey: T;
  /** 切换回调 */
  onChange: (key: T) => void;
}

/** 带下划线的共享页签栏（管理页高级设置风格）。 */
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
            data-tab={tab.key}
            aria-selected={selected}
            className={`${styles.tab} ${selected ? styles.active : ""}`}
            onClick={() => onChange(tab.key)}
          >
            <TabLabel icon={tab.icon}>
              {tab.fallback ? t(tab.labelKey, tab.fallback) : t(tab.labelKey)}
            </TabLabel>
          </button>
        );
      })}
    </div>
  );
}
