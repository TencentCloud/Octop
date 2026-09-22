import { useEffect, useState } from "react";
import { Button, Progress, Spin } from "antd";
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
  connectionLost?: boolean;
}

export default function MemoryMaintenanceBanner({
  status,
  blocking,
  connectionLost = false,
}: MemoryMaintenanceBannerProps) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  const [dismissed, setDismissed] = useState<string | null>(null);
  const terminal = ["done", "failed", "skipped"].includes(status.phase);
  const resultKey = `${status.started_at ?? status.updated_at ?? ""}:${
    status.phase
  }`;

  useEffect(() => {
    if (terminal) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [terminal]);

  const end = terminal
    ? status.updated_at ?? status.started_at ?? now / 1000
    : now / 1000;
  const elapsed = status.started_at
    ? Math.max(0, Math.floor(end - status.started_at))
    : 0;
  const size = formatBytes(status.file_bytes);
  const title = t(`chat.memoryMaintenance.${status.phase}`, {
    defaultValue: t("chat.memoryMaintenance.compacting"),
  });
  const hint = terminal
    ? t(`chat.memoryMaintenance.hint_${status.phase}`)
    : status.phase === "waiting"
    ? t("chat.memoryMaintenance.hintWaiting")
    : blocking
    ? t("chat.memoryMaintenance.hintBlocking")
    : t("chat.memoryMaintenance.hintQueued");

  if (terminal && dismissed === resultKey) return null;

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
        {terminal ? (
          <Button
            type="text"
            size="small"
            onClick={() => setDismissed(resultKey)}
          >
            {t("chat.memoryMaintenance.dismiss")}
          </Button>
        ) : null}
      </div>
      <div className={styles.hint}>{hint}</div>
      {connectionLost && !terminal ? (
        <div className={styles.hint} role="alert">
          {t("chat.memoryMaintenance.connectionLost")}
        </div>
      ) : blocking && elapsed >= 60 ? (
        <div className={styles.hint}>
          {t("chat.memoryMaintenance.longRunning")}
        </div>
      ) : null}
      {!terminal && status.scanned != null && status.total != null ? (
        <div>
          {t("chat.memoryMaintenance.scanned", {
            count: status.scanned,
            total: status.total,
          })}
        </div>
      ) : null}
      {terminal ? null : status.percent != null ? (
        <Progress
          percent={status.percent}
          status="active"
          showInfo={false}
          size="small"
        />
      ) : (
        <Spin size="small" />
      )}
    </div>
  );
}
