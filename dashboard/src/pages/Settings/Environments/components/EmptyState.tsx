import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";
import cx from "classnames";
import styles from "../index.module.less";

interface EmptyStateProps {
  className?: string;
}

export function EmptyState({ className }: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <div className={cx(styles.emptyState, className)}>
      <span className={styles.emptyIcon}>
        <KeyRound size={36} strokeWidth={1.2} />
      </span>
      <span>{t("environments.noVariables")}</span>
    </div>
  );
}
