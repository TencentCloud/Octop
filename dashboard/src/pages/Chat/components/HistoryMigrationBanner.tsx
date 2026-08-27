import { Button } from "antd";
import { useTranslation } from "react-i18next";
import type { HistoryMigrationStatus } from "../../../api/modules/octopThreads";
import styles from "./HistoryMigrationBanner.module.less";

interface HistoryMigrationBannerProps {
  status: HistoryMigrationStatus;
  starting: boolean;
  startFailed: boolean;
  onStart: () => void;
}

export default function HistoryMigrationBanner({
  status,
  starting,
  startFailed,
  onStart,
}: HistoryMigrationBannerProps) {
  const { t } = useTranslation();
  const active = status.processing;
  const canQueueMore = status.can_start && status.pending + status.failed > 0;
  const failedHint = startFailed || (status.failed > 0 && !active);

  return (
    <div className={styles.banner} role="status">
      <div className={styles.content}>
        <div className={styles.title}>
          {t("chat.historyMigration.title", { count: status.remaining })}
        </div>
        <div className={failedHint ? styles.errorHint : styles.hint}>
          {startFailed
            ? t("chat.historyMigration.startFailed")
            : active
            ? t("chat.historyMigration.runningHint")
            : status.agent_busy
            ? t("chat.historyMigration.agentBusyHint")
            : !status.can_start
            ? t("chat.historyMigration.queueBusyHint")
            : status.failed > 0
            ? t("chat.historyMigration.retryHint", { count: status.failed })
            : t("chat.historyMigration.readyHint")}
        </div>
        {active && (
          <div
            className={styles.progressTrack}
            role="progressbar"
            aria-label={t("chat.historyMigration.running")}
          >
            <span className={styles.progressBar} />
          </div>
        )}
      </div>
      <Button
        size="small"
        type={active ? "default" : "primary"}
        loading={starting}
        disabled={!status.can_start || (active && !canQueueMore)}
        onClick={onStart}
      >
        {active
          ? canQueueMore
            ? t("chat.historyMigration.queueRest")
            : t("chat.historyMigration.running")
          : !status.can_start
          ? t("chat.historyMigration.waiting")
          : status.failed > 0
          ? t("chat.historyMigration.retry")
          : t("chat.historyMigration.start")}
      </Button>
    </div>
  );
}
