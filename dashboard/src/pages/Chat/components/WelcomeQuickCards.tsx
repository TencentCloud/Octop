import { useTranslation } from "react-i18next";
import { iconForName } from "../../Experts/components/iconForName";
import { pastelIconBackground } from "../../../utils/pastelIconBackground";
import type { WelcomeQuickCard } from "./WelcomeScreen";
import styles from "../index.module.less";

interface WelcomeQuickCardsProps {
  cards: WelcomeQuickCard[];
  showToggle: boolean;
  expanded: boolean;
  onToggle: () => void;
  onPromptClick: (text: string) => void;
  sectionTitleRef: React.Ref<HTMLSpanElement>;
}

export default function WelcomeQuickCards({
  cards,
  showToggle,
  expanded,
  onToggle,
  onPromptClick,
  sectionTitleRef,
}: WelcomeQuickCardsProps) {
  const { t } = useTranslation();

  if (cards.length === 0) return null;

  return (
    <div className={styles.quickSection}>
      <span className={styles.quickSectionTitle} ref={sectionTitleRef}>
        {t("chatWelcome.promptSectionTitle")}
      </span>
      <div className={styles.quickCards}>
        {cards.map((card, i) => (
          <button
            key={`${card.title}-${i}`}
            type="button"
            className={styles.quickCard}
            style={{ animationDelay: `${i * 40}ms` }}
            onClick={() => onPromptClick(card.prompt)}
          >
            <div
              className={styles.quickCardIcon}
              style={{
                background: pastelIconBackground(card.color, i),
                color: "rgba(15,23,42,0.55)",
              }}
            >
              {iconForName(card.icon_name, 18)}
            </div>
            <div className={styles.quickCardBody}>
              <span className={styles.quickCardTitle}>{card.title}</span>
              <span className={styles.quickCardDesc}>{card.description}</span>
            </div>
          </button>
        ))}
      </div>
      {showToggle && (
        <button
          type="button"
          aria-label={
            expanded ? t("chatWelcome.showLess") : t("chatWelcome.showMore")
          }
          className={`${styles.quickMoreButton}${
            expanded ? ` ${styles.quickMoreButtonExpanded}` : ""
          }`}
          onClick={onToggle}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
      )}
    </div>
  );
}

interface WelcomeQuickCardProbeProps {
  probeRef: React.Ref<HTMLDivElement>;
}

export function WelcomeQuickCardProbe({
  probeRef,
}: WelcomeQuickCardProbeProps) {
  return (
    <div
      ref={probeRef}
      aria-hidden
      className={`${styles.quickCard} ${styles.quickCardProbe}`}
    >
      <div className={styles.quickCardIcon} />
      <div className={styles.quickCardBody}>
        <span className={styles.quickCardTitle}>probe</span>
        <span className={styles.quickCardDesc}>probe</span>
      </div>
    </div>
  );
}
