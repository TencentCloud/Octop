import { Button, Result, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import type { OctopAgent } from "../../../context/AgentContext";
import {
  formatAgentError,
  isAgentModelConfigError,
} from "../../../utils/agentError";
import styles from "../index.module.less";
import ModelConfigEmpty from "./ModelConfigEmpty";

interface AgentNotReadyScreenProps {
  agent: OctopAgent | null;
  noAgents?: boolean;
  loading?: boolean;
  /** Whether this user may open the model settings themselves. */
  canConfigureModels?: boolean;
}

export default function AgentNotReadyScreen({
  agent,
  noAgents = false,
  loading = false,
  canConfigureModels = true,
}: AgentNotReadyScreenProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className={styles.agentNotReady}>
        <Spin />
      </div>
    );
  }

  if (noAgents) {
    return (
      <div className={styles.noAgentsEmpty}>
        <div className={styles.noAgentsEmptyInner}>
          <div className={styles.noAgentsEmptyIcon}>
            <OctopEmptyMascot className={styles.noAgentsEmptyMascot} />
          </div>
          <h1 className={styles.noAgentsEmptyTitle}>
            {t("chat.noAgentsTitle")}
          </h1>
          <p className={styles.noAgentsEmptyHint}>{t("chat.noAgentsHint")}</p>
          <Button
            type="primary"
            size="large"
            onClick={() => navigate("/experts")}
          >
            {t("chat.createExpert")}
          </Button>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className={styles.agentNotReady}>
        <Result status="info" title={t("chat.pickAgent")} />
      </div>
    );
  }

  const state = agent.state;
  const errorText = formatAgentError(agent.last_error, t);
  const isModelError = isAgentModelConfigError(agent.last_error);
  const disconnected = Boolean(agent.bridge && agent.bridge_disconnected);

  /**
   * "No model configured" reaches us as an agent start failure, so this screen
   * used to answer a setup step with a red cross and "专家启动失败" — the exact
   * alarm reserved for a broken agent. Nothing failed here: the friendly
   * prompt already exists for that case, so show it. A disconnected bridge
   * still wins, because that is the state the user has to act on right now and
   * last_error may only be a leftover.
   */
  if (state === "failed" && isModelError && !disconnected) {
    return <ModelConfigEmpty canConfigure={canConfigureModels} />;
  }

  let title = t("chat.agentNotRunning");
  let subTitle = t("chat.agentNotRunningHint");

  if (disconnected) {
    const inbound = Boolean(agent.bridge_inbound);
    title = t("chat.remoteExpert.disconnectedTitle");
    subTitle = inbound
      ? agent.bridge_connection_name
        ? t("chat.remoteExpert.waitForPeerNamed", {
            name: agent.bridge_connection_name,
          })
        : t("chat.remoteExpert.waitForPeer")
      : agent.bridge_connection_name
      ? t("chat.remoteExpert.disconnectedHintNamed", {
          name: agent.bridge_connection_name,
        })
      : t("chat.remoteExpert.disconnectedHint");
  } else if (state === "failed") {
    title = t("chat.agentFailed");
    subTitle = errorText || t("chat.agentFailedHint");
  } else if (state === "stopped" || state === "created") {
    title = t("chat.agentNotRunning");
    subTitle = t("chat.agentNotRunningHint");
  } else if (state === "starting" || state === "stopping") {
    title = t("chat.agentStarting");
    subTitle = t("chat.agentStartingHint");
  }

  return (
    <div className={styles.agentNotReady}>
      <Result
        status={
          disconnected
            ? "warning"
            : state === "failed"
            ? "error"
            : state === "stopped" || state === "created"
            ? "warning"
            : "info"
        }
        title={title}
        subTitle={subTitle}
        extra={
          disconnected ? (
            <Button type="primary" onClick={() => navigate("/bridge")}>
              {t(
                agent.bridge_inbound
                  ? "chat.remoteExpert.openBridge"
                  : "chat.remoteExpert.reconnect",
              )}
            </Button>
          ) : (
            <Button type="primary" onClick={() => navigate("/experts")}>
              {t("chat.goToExperts")}
            </Button>
          )
        }
      />
    </div>
  );
}
