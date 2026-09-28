import { Alert } from "antd";
import { useTranslation } from "react-i18next";

interface PeerOnlyRemoteAlertProps {
  /** i18n key under ``chat.remoteExpert``. */
  hintKey: "peerOnlyAcp" | "peerOnlyBrowser";
  style?: React.CSSProperties;
}

/** Local-only surfaces (ACP runners on this host, Remote Browser install). */
export default function PeerOnlyRemoteAlert({
  hintKey,
  style,
}: PeerOnlyRemoteAlertProps) {
  const { t } = useTranslation();
  return (
    <Alert
      type="info"
      showIcon
      message={t("chat.remoteExpert.peerOnlyTitle")}
      description={t(`chat.remoteExpert.${hintKey}`)}
      style={{ marginBottom: 12, ...style }}
    />
  );
}
