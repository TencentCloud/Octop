import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, GraduationCap, Info } from "lucide-react";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import { message } from "@/utils/antdMessage";
import ExpertAgentAvatar, { type ChatAgentOption } from "./ExpertAgentAvatar";
import RemoteExpertHint from "./RemoteExpertHint";
import { groupExpertsByConnection } from "../../../utils/remoteExpert";
import { useHiddenSharedExperts } from "../hooks/useHiddenSharedExperts";
import styles from "../index.module.less";

export type { ChatAgentOption };

interface ExpertPickerPopoverProps {
  agents: ChatAgentOption[];
  selectedAgentIds: string[];
  onSelect: (agent: ChatAgentOption) => void;
  onNavigateAway?: () => void;
  remoteManaged?: boolean;
}

export default function ExpertPickerPopover({
  agents,
  selectedAgentIds,
  onSelect,
  onNavigateAway,
  remoteManaged = false,
}: ExpertPickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [showingHidden, setShowingHidden] = useState(false);
  const { filterVisible, pickHidden, hide, unhide, canHide } =
    useHiddenSharedExperts();

  const hiddenAgents = useMemo(() => pickHidden(agents), [agents, pickHidden]);
  const visibleAgents = useMemo(
    () =>
      filterVisible(agents, {
        keepAgentIds: selectedAgentIds,
      }),
    [agents, filterVisible, selectedAgentIds],
  );

  // Leave the hidden-only view once nothing remains hidden.
  const viewingHidden = showingHidden && hiddenAgents.length > 0;
  const listAgents = viewingHidden ? hiddenAgents : visibleAgents;
  const grouped = useMemo(
    () => groupExpertsByConnection(listAgents, t("agentSelector.localGroup")),
    [listAgents, t],
  );
  const showGroups = grouped.length > 1;
  const pickerItems = useMemo(
    () => (showGroups ? grouped.flatMap((group) => group.agents) : listAgents),
    [grouped, listAgents, showGroups],
  );

  const filterFn = useCallback(
    (agent: ChatAgentOption, query: string) =>
      agent.name.toLowerCase().includes(query) ||
      agent.agent_id.toLowerCase().includes(query),
    [],
  );

  return (
    <SearchablePickerPanel
      items={pickerItems}
      filterFn={filterFn}
      searchPlaceholder={
        viewingHidden
          ? t("chat.expertPickerHiddenSearch")
          : t("chat.expertPickerSearch")
      }
      emptyMessage={
        viewingHidden
          ? t("chat.expertPickerHiddenEmpty")
          : t("chat.expertPickerEmpty")
      }
      width="compact"
      getGroupKey={
        showGroups
          ? (agent) =>
              agent.bridge
                ? agent.bridge_connection_id ??
                  agent.bridge_connection_name ??
                  "_"
                : "local"
          : undefined
      }
      renderGroupHeader={
        showGroups
          ? (key, first) => (
              <div className={styles.expertPickerGroup}>
                {first.bridge
                  ? `${first.bridge_connection_name || key}${
                      first.bridge_disconnected
                        ? ` · ${t("agentSelector.disconnected")}`
                        : ""
                    }`
                  : t("agentSelector.localGroup")}
              </div>
            )
          : undefined
      }
      footerIcon={
        remoteManaged ? (
          <Info size={15} aria-hidden />
        ) : (
          <GraduationCap size={15} aria-hidden />
        )
      }
      footerLabel={
        remoteManaged
          ? t("chat.remoteExpert.manageOnPeer")
          : t("chat.expertPickerManage")
      }
      footerMuted={remoteManaged}
      onFooterClick={() => {
        if (remoteManaged) {
          message.info(t("chat.remoteExpert.manageToast"));
          return;
        }
        onNavigateAway?.();
        navigate("/experts");
      }}
      beforeFooter={
        hiddenAgents.length > 0 ? (
          <button
            type="button"
            className={styles.expertHiddenToggle}
            onClick={() => setShowingHidden((v) => !v)}
          >
            {viewingHidden
              ? t("chat.expertPickerShowVisible")
              : t("chat.expertPickerHidden", { count: hiddenAgents.length })}
          </button>
        ) : null
      }
      renderItem={(agent) => {
        const active = selectedAgentIds.includes(agent.agent_id);
        const hideable = canHide(agent);
        return (
          <div
            key={agent.agent_id}
            className={`${styles.skillPickerItem} ${
              active ? styles.expertPickerItemActive : ""
            } ${styles.expertPickerRow}`}
          >
            <button
              type="button"
              className={styles.expertPickerSelect}
              onClick={() => onSelect(agent)}
            >
              <ExpertAgentAvatar
                iconName={agent.icon_name}
                iconUrl={agent.icon_url}
                color={agent.color}
                size={32}
                iconSize={18}
              />
              <span className={styles.expertPickerItemText}>
                <span className={pickerStyles.itemName}>{agent.name}</span>
                {agent.is_shared && (
                  <span className={styles.expertSharedBadge}>
                    {t("chat.expertSharedBadge", "共享")}
                  </span>
                )}
                <RemoteExpertHint agent={agent} />
              </span>
            </button>
            {hideable ? (
              <button
                type="button"
                className={styles.expertHideBtn}
                title={
                  viewingHidden ? t("chat.expertUnhide") : t("chat.expertHide")
                }
                aria-label={
                  viewingHidden ? t("chat.expertUnhide") : t("chat.expertHide")
                }
                onClick={(e) => {
                  e.stopPropagation();
                  if (viewingHidden) unhide(agent.agent_id);
                  else hide(agent.agent_id);
                }}
              >
                {viewingHidden ? <Eye size={15} /> : <EyeOff size={15} />}
              </button>
            ) : null}
          </div>
        );
      }}
    />
  );
}
