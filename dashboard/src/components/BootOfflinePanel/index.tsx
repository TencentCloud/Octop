import { Button, Result } from "antd";
import { useTranslation } from "react-i18next";

interface BootOfflinePanelProps {
  /** Defaults to a full page reload. */
  onRetry?: () => void;
}

/**
 * Full-viewport panel when startup health / setup / auth probes cannot reach
 * the API (offline or backend down). Prefer this over a blank spinner shell.
 */
export default function BootOfflinePanel({ onRetry }: BootOfflinePanelProps) {
  const { t } = useTranslation();

  const handleRetry = () => {
    if (onRetry) {
      onRetry();
      return;
    }
    window.location.reload();
  };

  return (
    <div
      role="alert"
      style={{
        height: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--fn-bg-layout, #f7f8fa)",
        padding: 24,
        boxSizing: "border-box",
      }}
    >
      <Result
        status="warning"
        title={t("errors.offlineTitle")}
        subTitle={t("errors.offlineSubtitle")}
        extra={
          <Button type="primary" onClick={handleRetry}>
            {t("errors.retry")}
          </Button>
        }
      />
    </div>
  );
}
