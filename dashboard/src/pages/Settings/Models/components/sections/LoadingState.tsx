/**
 * LoadingState — finnie-equivalent loading/error pane.
 *
 * Identical to finnie's
 * ``dashboard/src/pages/Settings/Models/components/sections/LoadingState.tsx``
 * except labels are translated via i18n.
 */
import { Button } from "antd";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import styles from "../../index.module.less";

interface LoadingStateProps {
  message: string;
  error?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function LoadingState({
  message,
  error,
  onRetry,
  className,
}: LoadingStateProps) {
  const { t } = useTranslation();
  return (
    <div className={cx(styles.loading, className)}>
      <span
        className={styles.loadingText}
        style={{ color: error ? "var(--fn-color-danger)" : undefined }}
      >
        {message}
      </span>
      {error && onRetry && (
        <Button onClick={onRetry} style={{ marginTop: 12 }}>
          {t("models.retry")}
        </Button>
      )}
    </div>
  );
}
