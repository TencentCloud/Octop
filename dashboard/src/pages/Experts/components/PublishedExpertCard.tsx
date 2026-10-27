import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import { App, Button, Dropdown } from "antd";
import { Download, MoreHorizontal } from "lucide-react";
import { ExpertIcon } from "./iconForName";
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
  const { modal, message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const accent = expert.color || "var(--fn-color-brand)";

  const confirmUnpublish = () => {
    modal.confirm({
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
      <div className={styles.marketCardHeader}>
        <div
          className={styles.agentCardIcon}
          style={{ color: accent, background: `${accent}18` }}
        >
          <ExpertIcon
            iconUrl={expert.icon_url}
            iconName={expert.icon_name}
            size={expert.icon_url ? 36 : 20}
            className={expert.icon_url ? styles.marketIconImg : undefined}
          />
        </div>
        <div className={styles.agentCardTitleBlock}>
          <div className={styles.marketCardTitleRow}>
            <div className={styles.agentCardName}>{expert.name}</div>
            <div className={styles.expertInstalledLabel}>
              {t("experts.published.badge")}
            </div>
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
      <div className={styles.marketCardFooter}>
        <div className={styles.marketCardFooterStart}>
          {expert.creator_username && (
            <span className={styles.marketMeta}>
              {t("experts.published.by", { name: expert.creator_username })}
            </span>
          )}
        </div>
        <Button
          size="small"
          type="primary"
          icon={<Download size={14} />}
          onClick={(event) => {
            event.stopPropagation();
            onInstall(expert);
          }}
        >
          {t("experts.published.install")}
        </Button>
      </div>
    </div>
  );
});
