import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Switch } from "antd";
import { Info, Settings2 } from "lucide-react";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import { message } from "@/utils/antdMessage";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { knowledgeIconForName } from "../../KnowledgeBases/knowledgeIcons";
import styles from "../index.module.less";

interface KnowledgePickerPopoverProps {
  knowledgeBases: KnowledgeBase[];
  selectedKnowledgeBaseIds: string[];
  onKnowledgeBaseIdsChange: (ids: string[]) => void;
  onNavigateAway?: () => void;
  remoteManaged?: boolean;
}

export default function KnowledgePickerPopover({
  knowledgeBases,
  selectedKnowledgeBaseIds,
  onKnowledgeBaseIdsChange,
  onNavigateAway,
  remoteManaged = false,
}: KnowledgePickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const currentUserId = useCurrentUser()?.id ?? null;

  const filterFn = useCallback(
    (knowledgeBase: KnowledgeBase, query: string) =>
      knowledgeBase.name.toLowerCase().includes(query) ||
      knowledgeBase.description.toLowerCase().includes(query),
    [],
  );

  return (
    <SearchablePickerPanel
      items={knowledgeBases}
      filterFn={filterFn}
      searchPlaceholder={t("chat.knowledgePickerSearch")}
      emptyMessage={t("chat.knowledgePickerEmpty")}
      width="narrow"
      footerIcon={
        remoteManaged ? (
          <Info size={15} aria-hidden />
        ) : (
          <Settings2 size={15} aria-hidden />
        )
      }
      footerLabel={
        remoteManaged
          ? t("chat.remoteExpert.manageOnPeer")
          : t("chat.manageKnowledgeBases")
      }
      footerMuted={remoteManaged}
      onFooterClick={() => {
        if (remoteManaged) {
          message.info(t("chat.remoteExpert.manageToast"));
          return;
        }
        onNavigateAway?.();
        navigate("/knowledge-bases");
      }}
      renderItem={(knowledgeBase) => {
        const active = selectedKnowledgeBaseIds.includes(knowledgeBase.id);
        return (
          <div
            key={knowledgeBase.id}
            className={`${styles.connectorPickerItem} ${
              active ? styles.connectorPickerItemActive : ""
            }`}
          >
            <span className={styles.knowledgePickerAvatar}>
              {knowledgeIconForName(knowledgeBase.icon_name, 16)}
            </span>
            <span className={pickerStyles.itemText}>
              <span className={pickerStyles.itemName}>
                {knowledgeBase.name}
              </span>
              {knowledgeBase.default_open &&
              currentUserId != null &&
              knowledgeBase.owner_user_id === currentUserId ? (
                <span className={pickerStyles.itemDesc}>
                  {t("knowledgeBases.defaultOpenBadge")}
                </span>
              ) : knowledgeBase.description ? (
                <span className={pickerStyles.itemDesc}>
                  {knowledgeBase.description}
                </span>
              ) : null}
            </span>
            <Switch
              size="small"
              className={styles.connectorPickerSwitch}
              checked={active}
              onChange={(checked) => {
                const next = checked
                  ? [...selectedKnowledgeBaseIds, knowledgeBase.id]
                  : selectedKnowledgeBaseIds.filter(
                      (id) => id !== knowledgeBase.id,
                    );
                onKnowledgeBaseIdsChange(next);
              }}
            />
          </div>
        );
      }}
    />
  );
}
