import { useTranslation } from "react-i18next";
import { useElapsedSince } from "../../../hooks/useElapsedSeconds";
import styles from "../index.module.less";

interface GeneratingIndicatorProps {
  onCancel?: () => void;
  /** When set, appends elapsed seconds (useful while waiting for the first token). */
  startedAt?: number | null;
  showElapsed?: boolean;
}

/** Single bottom waiting state for the whole turn — replaces thinking/continuing. */
export default function GeneratingIndicator({
  onCancel,
  startedAt = null,
  showElapsed = false,
}: GeneratingIndicatorProps) {
  const { t } = useTranslation();
  const elapsedAnchor =
    startedAt != null && startedAt > 0 ? startedAt : Date.now();
  const elapsed = useElapsedSince(elapsedAnchor);
  const showTimer = Boolean(showElapsed && startedAt != null && startedAt > 0);

  return (
    <div
      className={styles.generatingIndicator}
      role="status"
      aria-live="polite"
    >
      <span className={styles.thinkingDot} />
      <span className={styles.thinkingDot} />
      <span className={styles.thinkingDot} />
      <span className={styles.generatingText}>
        {showTimer
          ? t("chat.generatingWithElapsed", {
              seconds: elapsed,
              defaultValue: "生成中 · {{seconds}}s",
            })
          : t("chat.generating", "生成中")}
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
  );
}
