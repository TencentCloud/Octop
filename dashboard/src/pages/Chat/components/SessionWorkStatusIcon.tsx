import { Loader2, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SessionWorkStatus } from "../utils/sessionWorkStatus";
import styles from "../index.module.less";

export default function SessionWorkStatusIcon({
  status,
}: {
  status: SessionWorkStatus;
}) {
  const { t } = useTranslation();
  if (status === "idle") return null;
  if (status === "waiting") {
    const label = t("chat.sessionWaiting");
    return (
      <span
        className={styles.sessionRowWaitingIcon}
        title={label}
        aria-label={label}
      >
        <Clock size={12} strokeWidth={2.25} aria-hidden />
      </span>
    );
  }
  const label = t("chat.sessionWorking");
  return (
    <span
      className={styles.sessionRowWorkingSpinner}
      title={label}
      aria-label={label}
    >
      <Loader2 size={12} strokeWidth={2.25} aria-hidden />
    </span>
  );
}
