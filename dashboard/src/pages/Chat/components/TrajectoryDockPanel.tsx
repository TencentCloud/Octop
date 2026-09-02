import { Empty, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { useTrajectorySession } from "../hooks/useTrajectorySession";
import dockStyles from "../index.module.less";
import styles from "./TrajectoryDockPanel.module.less";
import TrajectoryLedger from "./TrajectoryLedger";

interface TrajectoryDockPanelProps {
  agentId?: string;
  threadId?: string | null;
  /** False while the dock is closed or another tab is active (keep-alive). */
  visible?: boolean;
}

export default function TrajectoryDockPanel({
  agentId,
  threadId = null,
  visible = true,
}: TrajectoryDockPanelProps) {
  const { t } = useTranslation();
  const { events, loading, error, retry } = useTrajectorySession({
    agentId,
    threadId,
    visible,
  });

  if (!threadId) {
    return (
      <div className={dockStyles.dockFileListEmpty}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectorySelectSession",
            "Select a session to view trajectory",
          )}
        />
      </div>
    );
  }

  if (loading && events.length === 0) {
    return (
      <div className={styles.status}>
        <Spin size="small" />
      </div>
    );
  }

  if (error && events.length === 0) {
    return (
      <div className={styles.status}>
        <p className={styles.errorText}>
          {t("chat.dockTrajectoryLoadError", "Failed to load trajectory")}
        </p>
        <button type="button" className={styles.retry} onClick={retry}>
          {t("chat.retry", "Retry")}
        </button>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className={dockStyles.dockFileListEmpty}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t(
            "chat.dockTrajectoryEmpty",
            "No trajectory events yet",
          )}
        />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <TrajectoryLedger events={events} />
    </div>
  );
}
