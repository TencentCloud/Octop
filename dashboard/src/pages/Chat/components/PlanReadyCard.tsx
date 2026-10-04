import { useTranslation } from "react-i18next";
import { ListTodo } from "lucide-react";
import styles from "./PlanReadyCard.module.less";

export interface PlanReadyCardProps {
  path: string;
  onExecute: () => void;
  onKeepEditing: () => void;
}

export default function PlanReadyCard({
  path,
  onExecute,
  onKeepEditing,
}: PlanReadyCardProps) {
  const { t } = useTranslation();
  return (
    <div
      className={`${styles.card} wb-intervention wb-plan`}
      data-testid="plan-ready-card"
    >
      <div className={styles.titleRow}>
        <span className={styles.iconWrap}>
          <ListTodo size={16} />
        </span>
        <div className={styles.title}>
          {t("chat.conversationMode.planReadyTitle")}
        </div>
      </div>
      <p className={styles.body}>
        {t("chat.conversationMode.planReadyBody", { path })}
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={`${styles.execute} wb-intervention__primary`}
          onClick={onExecute}
        >
          {t("chat.conversationMode.execute")}
        </button>
        <button
          type="button"
          className={`${styles.keep} wb-intervention__secondary`}
          onClick={onKeepEditing}
        >
          {t("chat.conversationMode.keepEditing")}
        </button>
      </div>
    </div>
  );
}
