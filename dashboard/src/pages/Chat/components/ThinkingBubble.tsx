import { useTranslation } from "react-i18next";
import { useElapsedSince } from "../../../hooks/useElapsedSeconds";
import styles from "../index.module.less";

interface ThinkingBubbleProps {
  onCancel?: () => void;
  startedAt: number;
}

export default function ThinkingBubble({
  onCancel,
  startedAt,
}: ThinkingBubbleProps) {
  const { t } = useTranslation();
  const typingSrc = `${import.meta.env.BASE_URL}octop-mascot-type.webm`;
  const elapsed = useElapsedSince(startedAt);

  return (
    <div className={styles.thinkingBubble}>
      <div className={styles.avatarCol}>
        <div className={styles.botAvatar}>
          <video
            src={typingSrc}
            autoPlay
            loop
            muted
            playsInline
            aria-label="Octop"
            ref={(el) => {
              if (el) el.muted = true;
            }}
          />
        </div>
      </div>
      <div className={styles.thinkingContent}>
        <span className={styles.thinkingDot} />
        <span className={styles.thinkingDot} />
        <span className={styles.thinkingDot} />
        <span className={styles.thinkingText}>
          {t("chat.thinking")}
          {` · ${elapsed}s`}
        </span>
        {onCancel && (
          <button
            className={styles.thinkingCancelBtn}
            onClick={onCancel}
            type="button"
            title={t("common.cancel")}
          >
            {t("common.cancel")}
          </button>
        )}
      </div>
    </div>
  );
}
