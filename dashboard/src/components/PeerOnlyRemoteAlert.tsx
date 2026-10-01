import { Alert } from "antd";
import { useTranslation } from "react-i18next";
import { useAgent } from "../context/AgentContext";

interface PeerOnlyRemoteAlertProps {
  /** i18n key under ``chat.remoteExpert``. */
  hintKey: "peerOnlyAcp" | "peerOnlyBrowser";
  style?: React.CSSProperties;
}

/** Host-only surfaces (ACP runners on this machine, Remote Browser). */
export default function PeerOnlyRemoteAlert({
  hintKey,
  style,
}: PeerOnlyRemoteAlertProps) {
  const { t } = useTranslation();
  const { agents, activeAgentId } = useAgent();
  const isPeer = agents.some(
    (agent) => agent.agent_id === activeAgentId && agent.bridge,
  );
  if (!isPeer) return null;
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
