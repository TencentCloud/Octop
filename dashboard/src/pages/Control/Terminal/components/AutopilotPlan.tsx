import { Button } from "antd";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import type {
  AutopilotStatus,
  AutopilotStep,
} from "../../../../hooks/useTerminalAutopilot";
import styles from "./AiPanel.module.less";

interface AutopilotPlanProps {
  status: AutopilotStatus;
  steps: AutopilotStep[];
  currentIndex: number;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRetry: () => void;
  onSkip: () => void;
  canStart: boolean;
}

export default function AutopilotPlan({
  status,
  steps,
  currentIndex,
  onStart,
  onPause,
  onResume,
  onStop,
  onRetry,
  onSkip,
  canStart,
}: AutopilotPlanProps) {
  const { t } = useTranslation();

  const total = steps.length;
  const current = total > 0 ? currentIndex + 1 : 0;

  return (
    <div className={styles.autopilotSection}>
      {steps.length > 0 && (
        <>
          <div className={styles.autopilotPlanTitle}>
            {t("terminal.ai.autopilotPlan")}
          </div>
          <div className={styles.autopilotStepCounter}>
            {t("terminal.ai.autopilotStepOf", { current, total })}
          </div>
          <ol className={styles.autopilotSteps}>
            {steps.map((step, idx) => (
              <li
                key={step.id}
                className={cx(
                  styles.autopilotStep,
                  styles[`autopilotStep_${step.status}`],
                  idx === currentIndex && styles.autopilotStepActive,
                )}
              >
                <code className={styles.autopilotStepCmd}>{step.command}</code>
              </li>
            ))}
          </ol>
        </>
      )}

      {status === "done" && (
        <div className={styles.autopilotStatusMsg}>
          {t("terminal.ai.autopilotDone")}
        </div>
      )}
      {status === "failed" && (
        <div className={styles.autopilotStatusMsgError}>
          {t("terminal.ai.autopilotFailed")}
        </div>
      )}

      <div className={styles.autopilotControls}>
        {(status === "idle" || status === "done" || status === "failed") && (
          <Button
            type="primary"
            size="small"
            disabled={!canStart}
            onClick={onStart}
          >
            {t("terminal.ai.autopilotStart")}
          </Button>
        )}
        {status === "running" && (
          <Button size="small" onClick={onPause}>
            {t("terminal.ai.autopilotPause")}
          </Button>
        )}
        {status === "paused" && (
          <Button type="primary" size="small" onClick={onResume}>
            {t("terminal.ai.autopilotResume")}
          </Button>
        )}
        {(status === "running" ||
          status === "paused" ||
          status === "planning") && (
          <Button size="small" danger onClick={onStop}>
            {t("terminal.ai.autopilotStop")}
          </Button>
        )}
        {status === "failed" && (
          <>
            <Button size="small" onClick={onRetry}>
              {t("terminal.ai.autopilotRetry")}
            </Button>
            <Button size="small" onClick={onSkip}>
              {t("terminal.ai.autopilotSkip")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
