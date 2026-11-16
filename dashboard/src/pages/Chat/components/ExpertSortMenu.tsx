import { useTranslation } from "react-i18next";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import { ArrowUpDown } from "lucide-react";
import type { ExpertSortMode } from "../utils/pinnedExpertsPrefs";
import styles from "../index.module.less";

const SORT_LABELS: Record<ExpertSortMode, { key: string; fallback: string }> = {
  recent: { key: "chat.expertSortRecent", fallback: "最近对话" },
  newest: { key: "chat.expertSortNewest", fallback: "最近创建" },
  oldest: { key: "chat.expertSortOldest", fallback: "最早创建" },
};

const SORT_ORDER: readonly ExpertSortMode[] = ["recent", "newest", "oldest"];

/** Sidebar control for expert order. Pins stay above every mode. */
export default function ExpertSortMenu({
  mode,
  onChange,
}: {
  mode: ExpertSortMode;
  onChange: (mode: ExpertSortMode) => void;
}) {
  const { t } = useTranslation();
  const labelFor = (value: ExpertSortMode) => {
    const meta = SORT_LABELS[value];
    return t(meta.key, meta.fallback);
  };
  const items: NonNullable<MenuProps["items"]> = SORT_ORDER.map((value) => ({
    key: value,
    label: labelFor(value),
    onClick: () => onChange(value),
  }));
  const current = labelFor(mode);
  return (
    <Dropdown
      menu={{ items, selectedKeys: [mode] }}
      trigger={["click"]}
      placement="bottomRight"
    >
      <button
        type="button"
        className={styles.expertSortBtn}
        aria-label={t("chat.expertSortLabel", "排序：{{mode}}", {
          mode: current,
        })}
        title={current}
      >
        <ArrowUpDown size={14} strokeWidth={2} aria-hidden />
      </button>
    </Dropdown>
  );
}
