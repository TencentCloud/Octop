import { Alert, Button } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

interface RemoteDisconnectBannerProps {
  connectionName?: string | null;
  style?: React.CSSProperties;
}

/** Shown while a cloud-collab expert stays selected after the link drops. */
export default function RemoteDisconnectBanner({
  connectionName,
  style,
}: RemoteDisconnectBannerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const name = (connectionName ?? "").trim();
  return (
    <Alert
      type="warning"
      showIcon
      message={t("chat.remoteExpert.disconnectedTitle")}
      description={
        name
          ? t("chat.remoteExpert.disconnectedHintNamed", { name })
          : t("chat.remoteExpert.disconnectedHint")
      }
      action={
        <Button size="small" onClick={() => navigate("/bridge")}>
          {t("chat.remoteExpert.reconnect")}
        </Button>
      }
      style={{ marginBottom: 12, ...style }}
    />
  );
}
