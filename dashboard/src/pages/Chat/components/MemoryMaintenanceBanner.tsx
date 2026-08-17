import { useEffect, useState } from "react";
import { Progress } from "antd";
import { useTranslation } from "react-i18next";
import type { MemoryMaintenanceStatus } from "../hooks/useMemoryMaintenance";
import styles from "./MemoryMaintenanceBanner.module.less";

function formatBytes(n?: number | null): string {
  if (!n || n <= 0) return "";
  const gb = 1024 ** 3;
  const mb = 1024 ** 2;
  if (n >= gb) return `${(n / gb).toFixed(1)} GB`;
  if (n >= mb) return `${Math.round(n / mb)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

interface MemoryMaintenanceBannerProps {
  status: MemoryMaintenanceStatus;
  blocking: boolean;
}

export default function MemoryMaintenanceBanner({
  status,
  blocking,
}: MemoryMaintenanceBannerProps) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const elapsed = status.started_at
    ? Math.max(0, Math.floor(now / 1000 - status.started_at))
    : 0;
  const size = formatBytes(status.file_bytes);
  const title = t(`chat.memoryMaintenance.${status.phase}`, {
    defaultValue: t("chat.memoryMaintenance.compacting"),
  });
  const hint = blocking
    ? t("chat.memoryMaintenance.hintBlocking")
    : t("chat.memoryMaintenance.hintQueued");

  return (
    <div className={styles.banner} role="status">
      <div className={styles.titleRow}>
        <span className={styles.title}>{title}</span>
        {size ? <span className={styles.meta}>{size}</span> : null}
        {elapsed > 0 ? (
          <span className={styles.meta}>
            {t("chat.memoryMaintenance.elapsed", { seconds: elapsed })}
          </span>
        ) : null}
      </div>
      <div className={styles.hint}>{hint}</div>
      <Progress
        percent={status.percent ?? 10}
        status="active"
        showInfo={false}
        size="small"
      />
    </div>
  );
}
