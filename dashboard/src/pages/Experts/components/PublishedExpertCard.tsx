import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dropdown, Modal } from "antd";
import { message } from "@/utils/antdMessage";
import { MoreHorizontal } from "lucide-react";
import { iconForName } from "./iconForName";
import {
  publishedExpertsApi,
  type PublishedExpert,
} from "../../../api/modules/publishedExperts";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "../index.module.less";

interface PublishedExpertCardProps {
  expert: PublishedExpert;
  canManage: boolean;
  onInstall: (expert: PublishedExpert) => void;
  onChanged: () => void;
}

export const PublishedExpertCard = memo(function PublishedExpertCard({
  expert,
  canManage,
  onInstall,
  onChanged,
}: PublishedExpertCardProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const accent = expert.color || "var(--fn-color-brand)";

  const confirmUnpublish = () => {
    Modal.confirm({
      title: t("experts.published.unpublishConfirm"),
      okText: t("experts.published.unpublish"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        setLoading(true);
        try {
          await publishedExpertsApi.unpublish(expert.id);
          message.success(t("experts.published.unpublishSuccess"));
          onChanged();
        } catch (err) {
          message.error(
            apiErrorMessage(err, t("experts.published.unpublishFailed"), t),
          );
        } finally {
          setLoading(false);
        }
      },
    });
  };

  return (
    <div
      className={styles.expertTemplateCard}
      onClick={() => onInstall(expert)}
      style={{ "--expert-accent": accent } as React.CSSProperties}
    >
      <div className={styles.expertTemplateHeader}>
        <div
          className={styles.agentCardIcon}
          style={{ color: accent, background: `${accent}18` }}
        >
          {iconForName(expert.icon_name, 20)}
        </div>
        <div className={styles.agentCardTitleBlock}>
          <div className={styles.agentCardName}>{expert.name}</div>
          <div className={styles.expertInstalledLabel}>
            {t("experts.published.badge")}
          </div>
        </div>
        {canManage && (
          <Dropdown
            menu={{
              items: [
                {
                  key: "unpublish",
                  danger: true,
                  label: t("experts.published.unpublish"),
                  onClick: ({ domEvent }) => {
                    domEvent.stopPropagation();
                    confirmUnpublish();
                  },
                },
              ],
            }}
            trigger={["click"]}
            disabled={loading}
          >
            <button
              type="button"
              className={styles.agentCard2NameActionBtn}
              aria-label={t("common.more", "More")}
              onClick={(event) => event.stopPropagation()}
            >
              <MoreHorizontal size={12} />
            </button>
          </Dropdown>
        )}
      </div>
      <div className={styles.agentCardDesc}>
        {expert.description || "\u00a0"}
      </div>
      <div className={styles.expertCardFooter}>
        <div className={styles.expertCardHint}>
          {t("experts.published.install")}
        </div>
        {expert.creator_username && (
          <div className={styles.expertInstalledLabel}>
            {t("experts.published.by", { name: expert.creator_username })}
          </div>
        )}
      </div>
    </div>
  );
});
