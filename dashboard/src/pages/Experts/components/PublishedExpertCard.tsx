import { memo } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "antd";
import { Download, Zap } from "lucide-react";
import { ExpertIcon } from "./iconForName";
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
      <div className={styles.marketCardHeader}>
        <div
          className={styles.agentCard2Icon}
          style={{
            color: accent,
            background: expert.icon_url ? "transparent" : `${accent}1a`,
          }}
        >
          <ExpertIcon
            iconUrl={expert.icon_url}
            iconName={expert.icon_name}
            size={expert.icon_url ? 42 : 22}
          />
        </div>
        <div className={styles.agentCardTitleBlock}>
          <div className={styles.marketCardTitleRow}>
            <div className={styles.agentCardName}>{expert.name}</div>
            {expert.creator_username && (
              <span className={styles.marketMeta}>
                {t("experts.published.by", { name: expert.creator_username })}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className={styles.agentCardDesc}>
        {expert.description || "\u00a0"}
      </div>
      <div className={styles.marketCardFooter}>
        <div className={styles.marketCardFooterStart}>
          <span className={styles.marketMeta}>
            <Zap size={13} />
            {t("experts.marketSkillCount", { count: expert.skill_count ?? 0 })}
          </span>
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
          {t("experts.createFromMarket")}
        </Button>
      </div>
    </div>
  );
});
