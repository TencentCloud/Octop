import { memo } from "react";
import { useTranslation } from "react-i18next";
import { iconForName } from "./iconForName";
import type { PublishedExpert } from "../../../api/modules/publishedExperts";
import styles from "../index.module.less";

interface PublishedExpertCardProps {
  expert: PublishedExpert;
  onInstall: (expert: PublishedExpert) => void;
}

export const PublishedExpertCard = memo(function PublishedExpertCard({
  expert,
  onInstall,
}: PublishedExpertCardProps) {
  const { t } = useTranslation();
  const accent = expert.color || "var(--fn-color-brand)";

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
