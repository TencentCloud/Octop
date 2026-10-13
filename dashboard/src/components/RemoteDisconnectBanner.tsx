import { Alert, Button } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

interface RemoteDisconnectBannerProps {
  connectionName?: string | null;
  /** Peer-initiated link: this side cannot redial. */
  inbound?: boolean;
  style?: React.CSSProperties;
}

/** Shown while a cloud-collab expert stays selected after the link drops. */
export default function RemoteDisconnectBanner({
  connectionName,
  inbound,
  style,
}: RemoteDisconnectBannerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const name = (connectionName ?? "").trim();
  const hint = inbound
    ? name
      ? t("chat.remoteExpert.waitForPeerNamed", { name })
      : t("chat.remoteExpert.waitForPeer")
    : name
    ? t("chat.remoteExpert.disconnectedHintNamed", { name })
    : t("chat.remoteExpert.disconnectedHint");
  return (
    <Alert
      type="warning"
      showIcon
      message={t("chat.remoteExpert.disconnectedTitle")}
      description={hint}
      action={
        <Button size="small" onClick={() => navigate("/bridge")}>
          {t(
            inbound
              ? "chat.remoteExpert.openBridge"
              : "chat.remoteExpert.reconnect",
          )}
        </Button>
      }
      style={{ marginBottom: 12, ...style }}
    />
  );
}
