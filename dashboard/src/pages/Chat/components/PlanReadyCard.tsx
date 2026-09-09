import { useTranslation } from "react-i18next";
import styles from "../index.module.less";
import { planBriefPreview } from "../utils/planArtifact";

interface PlanReadyCardProps {
  brief: string;
  onExecute: () => void;
  onContinue: () => void;
}

/** Cursor/WorkBuddy-style Plan → Craft checkpoint (#616 P6). */
export default function PlanReadyCard({
  brief,
  onExecute,
  onContinue,
}: PlanReadyCardProps) {
  const { t } = useTranslation();
  const preview = planBriefPreview(brief);
  return (
    <div className={styles.planReadyCard} data-testid="plan-ready-card">
      <div className={styles.planReadyTitle}>
        {t("chat.planReadyTitle", "按计划执行？")}
      </div>
      <p className={styles.planReadyHint}>
        {t(
          "chat.planReadyHint",
          "确认后将切换到默认模式并带着这份计划继续执行；也可继续改计划。",
        )}
      </p>
      {preview ? (
        <pre className={styles.planReadyBrief} data-testid="plan-ready-brief">
          {preview}
        </pre>
      ) : null}
      <div className={styles.planReadyActions}>
        <button
          type="button"
          className={styles.planReadyPrimary}
          data-testid="plan-ready-execute"
          onClick={onExecute}
        >
          {t("chat.planReadyExecute", "按计划执行")}
        </button>
        <button
          type="button"
          className={styles.planReadySecondary}
          data-testid="plan-ready-continue"
          onClick={onContinue}
        >
          {t("chat.planReadyContinue", "继续改计划")}
        </button>
      </div>
    </div>
  );
}
