// dashboard/src/pages/Experts/components/ExpertCard.tsx
import { memo } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle } from "lucide-react";
import { pickLocale } from "../../../utils/localizedText";
import { iconForName } from "./iconForName";
import styles from "../index.module.less";

export interface ExpertSummary {
  id: string;
  label: { zh?: string; en?: string };
  description: { zh?: string; en?: string };
  icon_name?: string | null;
  color?: string | null;
  files?: string[];
}

interface ExpertCardProps {
  expert: ExpertSummary;
  lang: "zh" | "en";
  isInstalled: boolean;
  onCreate: (expert: ExpertSummary) => void;
}

export const ExpertCard = memo(function ExpertCard({
  expert,
  lang,
  isInstalled,
  onCreate,
}: ExpertCardProps) {
  const { t } = useTranslation();
  const label = pickLocale(expert.label, lang) || expert.id;
  const desc = pickLocale(expert.description, lang);
  const accent = expert.color || "#E85D75";

  return (
    <div
      className={styles.expertTemplateCard}
      onClick={() => onCreate(expert)}
      style={
        {
          "--expert-accent": accent,
        } as React.CSSProperties
      }
    >
      {/* Icon + title */}
      <div className={styles.expertTemplateHeader}>
        <div
          className={styles.agentCardIcon}
          style={{
            color: accent,
            background: `${accent}18`,
          }}
        >
          {iconForName(expert.icon_name, 20)}
        </div>
        <div className={styles.agentCardTitleBlock}>
          <div className={styles.agentCardName}>{label}</div>
        </div>
      </div>

      {/* Description */}
      <div className={styles.agentCardDesc}>{desc || "\u00a0"}</div>

      {/* Footer */}
      <div className={styles.expertCardFooter}>
        <div className={styles.expertCardHint}>
          {t("experts.createFromTemplate")}
        </div>
        {isInstalled && (
          <div className={styles.expertInstalledLabel}>
            <CheckCircle size={12} />
            {t("experts.installedBadge")}
          </div>
        )}
      </div>
    </div>
  );
});
