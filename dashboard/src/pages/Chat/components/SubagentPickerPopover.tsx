import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import type { AgentSubagentSummary } from "../../../api/modules/subagents";
import styles from "../index.module.less";

interface SubagentPickerPopoverProps {
  subagents: AgentSubagentSummary[];
  selectedSlugs: string[];
  onSelect: (subagent: AgentSubagentSummary) => void;
  onNavigateAway?: () => void;
}

export default function SubagentPickerPopover({
  subagents,
  selectedSlugs,
  onSelect,
  onNavigateAway,
}: SubagentPickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const filterFn = useCallback(
    (subagent: AgentSubagentSummary, query: string) =>
      subagent.name.toLowerCase().includes(query) ||
      subagent.slug.toLowerCase().includes(query) ||
      (subagent.description || "").toLowerCase().includes(query),
    [],
  );

  return (
    <SearchablePickerPanel
      items={subagents}
      filterFn={filterFn}
      searchPlaceholder={t("chat.subagentPickerSearch")}
      emptyMessage={t("chat.subagentPickerEmpty")}
      width="compact"
      footerIcon={<Bot size={15} aria-hidden />}
      footerLabel={t("chat.subagentPickerManage")}
      onFooterClick={() => {
        onNavigateAway?.();
        navigate("/personalization/subagents");
      }}
      renderItem={(subagent) => {
        const active = selectedSlugs.includes(subagent.slug);
        return (
          <button
            key={subagent.slug}
            type="button"
            className={`${styles.skillPickerItem} ${
              active ? styles.subagentPickerItemActive : ""
            }`}
            onClick={() => onSelect(subagent)}
          >
            <span className={styles.skillPickerAvatar} aria-hidden>
              {subagent.emoji || "🤖"}
            </span>
            <span className={pickerStyles.itemText}>
              <span className={pickerStyles.itemName}>{subagent.name}</span>
              {subagent.description ? (
                <span className={pickerStyles.itemDesc}>
                  {subagent.description}
                </span>
              ) : (
                <span className={pickerStyles.itemDesc}>{subagent.slug}</span>
              )}
            </span>
          </button>
        );
      }}
    />
  );
}
