import { Empty } from "antd";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface TrajectoryDockPanelProps {
  agentId?: string;
  threadId?: string | null;
}

/**
 * Trajectory dock body. Ledger / live feed land in Task 12; this is the
 * empty-state shell so the tab can open from the floating toolbar.
 */
export default function TrajectoryDockPanel({
  threadId = null,
}: TrajectoryDockPanelProps) {
  const { t } = useTranslation();
  const description = threadId
    ? t("chat.dockTrajectoryEmpty", "No trajectory events yet")
    : t(
        "chat.dockTrajectorySelectSession",
        "Select a session to view trajectory",
      );

  return (
    <div className={styles.dockFileListEmpty}>
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
    </div>
  );
}
