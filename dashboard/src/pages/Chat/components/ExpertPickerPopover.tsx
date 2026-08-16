import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { GraduationCap } from "lucide-react";
import { Tag } from "antd";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import ExpertAgentAvatar, { type ChatAgentOption } from "./ExpertAgentAvatar";
import { isSharedExpertViewer } from "../../../utils/sharedExpert";
import styles from "../index.module.less";

export type { ChatAgentOption };

interface ExpertPickerPopoverProps {
  agents: ChatAgentOption[];
  selectedAgentIds: string[];
  onAgentsChange: (ids: string[]) => void;
  onNavigateAway?: () => void;
}

export default function ExpertPickerPopover({
  agents,
  selectedAgentIds,
  onAgentsChange,
  onNavigateAway,
}: ExpertPickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const filterFn = useCallback(
    (agent: ChatAgentOption, query: string) =>
      agent.name.toLowerCase().includes(query) ||
      agent.agent_id.toLowerCase().includes(query),
    [],
  );

  return (
    <SearchablePickerPanel
      items={agents}
      filterFn={filterFn}
      searchPlaceholder={t("chat.expertPickerSearch")}
      emptyMessage={t("chat.expertPickerEmpty")}
      width="compact"
      footerIcon={<GraduationCap size={15} aria-hidden />}
      footerLabel={t("chat.expertPickerManage")}
      onFooterClick={() => {
        onNavigateAway?.();
        navigate("/experts");
      }}
      renderItem={(agent) => {
        const active = selectedAgentIds.includes(agent.agent_id);
        return (
          <button
            key={agent.agent_id}
            type="button"
            className={`${styles.skillPickerItem} ${
              active ? styles.expertPickerItemActive : ""
            }`}
            onClick={() => {
              const next = active
                ? selectedAgentIds.filter((id) => id !== agent.agent_id)
                : [...selectedAgentIds, agent.agent_id];
              onAgentsChange(next);
            }}
          >
            <ExpertAgentAvatar
              iconName={agent.icon_name}
              color={agent.color}
              size={32}
              iconSize={18}
            />
            <span className={pickerStyles.itemText}>
              <span className={pickerStyles.itemName}>{agent.name}</span>
              {agent.is_shared && (
                <Tag color="blue">
                  {isSharedExpertViewer(agent)
                    ? t("experts.share.fromOwner", {
                        name: agent.owner_username,
                      })
                    : t("experts.share.badge")}
                </Tag>
              )}
            </span>
          </button>
        );
      }}
    />
  );
}
