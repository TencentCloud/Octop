import { Button, Result, Spin } from "antd";
import { Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import type { OctopAgent } from "../../../context/AgentContext";
import {
  formatAgentError,
  isAgentModelConfigError,
} from "../../../utils/agentError";
import styles from "../index.module.less";

interface AgentNotReadyScreenProps {
  agent: OctopAgent | null;
  noAgents?: boolean;
  loading?: boolean;
}

export default function AgentNotReadyScreen({
  agent,
  noAgents = false,
  loading = false,
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

  let title = t("chat.agentNotRunning");
  let subTitle = t("chat.agentNotRunningHint");

  if (state === "failed") {
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
          state === "failed"
            ? "error"
            : state === "stopped" || state === "created"
            ? "warning"
            : "info"
        }
        title={title}
        subTitle={subTitle}
        extra={
          isModelError ? (
            <Button
              type="primary"
              icon={<Settings size={14} />}
              onClick={() => navigate("/admin/models")}
            >
              {t("modelConfig.configureButton")}
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
