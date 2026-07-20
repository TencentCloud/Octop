import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWelcomeQuickCardsLayout } from "../hooks/useWelcomeQuickCardsLayout";
import WelcomeQuickCards, { WelcomeQuickCardProbe } from "./WelcomeQuickCards";
import styles from "../index.module.less";

// Idle (peeking) is the default; tap cycles to the typing variant.
const MASCOT_PEEK = "/octop-mascot-peek.webm";
const MASCOT_TYPE = "/octop-mascot-type.webm";
const MASCOT_IMAGES = [MASCOT_PEEK, MASCOT_TYPE];

function getRandomMascot(current?: string): string {
  if (MASCOT_IMAGES.length <= 1) return MASCOT_IMAGES[0];
  let next = current;
  // Avoid picking the same image twice in a row.
  while (next === current) {
    next = MASCOT_IMAGES[Math.floor(Math.random() * MASCOT_IMAGES.length)];
  }
  return next as string;
}

export interface WelcomeQuickCard {
  title: string;
  description: string;
  prompt: string;
  color: string;
  icon_name?: string | null;
}

interface WelcomeScreenProps {
  onPromptClick: (text: string) => void;
  agentName?: string | null;
  welcomeSuffix?: string | null;
  quickCards: WelcomeQuickCard[];
  hideMascot?: boolean;
}

export default function WelcomeScreen({
  onPromptClick,
  agentName,
  welcomeSuffix,
  quickCards,
  hideMascot = false,
}: WelcomeScreenProps) {
  const { t } = useTranslation();
  const [mascotSrc, setMascotSrc] = useState(MASCOT_PEEK);
  const {
    welcomeRef,
    headingRef,
    sectionTitleRef,
    probeRef,
    expanded,
    setExpanded,
    cards,
    showToggle,
    autoHideMascot,
  } = useWelcomeQuickCardsLayout(quickCards);

  const handleMascotClick = () => {
    setMascotSrc((prev) => getRandomMascot(prev));
  };

  return (
    <div className={styles.welcome} ref={welcomeRef}>
      <div className={styles.welcomeInner}>
        <div className={styles.welcomeHeading} ref={headingRef}>
          {!hideMascot && !autoHideMascot && (
            <video
              key={mascotSrc}
              className={styles.welcomeMascot}
              src={mascotSrc}
              autoPlay
              loop
              muted
              playsInline
              aria-label="Octop mascot"
              draggable={false}
              onClick={handleMascotClick}
              role="button"
              tabIndex={0}
              title={t("chatWelcome.mascotSwitchHint")}
              ref={(el) => {
                if (el) el.muted = true;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleMascotClick();
                }
              }}
            />
          )}
          <h1 className={styles.welcomeTitle}>{t("chatWelcome.greeting")}</h1>
          <p className={styles.welcomeSubtitle}>
            {agentName ? (
              <>
                <span className={styles.welcomeAgentMention}>@{agentName}</span>
                <span className={styles.welcomeSubtitleText}>
                  {welcomeSuffix ?? t("chatWelcome.descriptionWithAgentSuffix")}
                </span>
              </>
            ) : (
              t("chatWelcome.description")
            )}
          </p>
        </div>

        {quickCards.length > 0 && (
          <WelcomeQuickCards
            cards={cards}
            showToggle={showToggle}
            expanded={expanded}
            onToggle={() => setExpanded((prev) => !prev)}
            onPromptClick={onPromptClick}
            sectionTitleRef={sectionTitleRef}
          />
        )}
      </div>

      {quickCards.length > 0 && <WelcomeQuickCardProbe probeRef={probeRef} />}
    </div>
  );
}
