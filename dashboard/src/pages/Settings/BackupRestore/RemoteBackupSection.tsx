import { useMemo, type ReactNode } from "react";
import { App, Select, Tag } from "antd";
import { Cloud, HardDrive } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  type BackupDestinationOption,
  type RemoteBackupSummary,
  type RemoteMirrorStatus,
} from "../../../api/modules/backup";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const LOCAL_VALUE = "local";

function statusColor(
  status: RemoteMirrorStatus | undefined,
): "success" | "warning" | "error" | "default" {
  if (status === "remote_ok") return "success";
  if (status === "unverified") return "warning";
  if (status === "remote_failed") return "error";
  return "default";
}

export function MirrorStatusTag({
  status,
  emptyKey = "backup.remoteStatusLocalOnly",
}: {
  status: RemoteMirrorStatus | undefined;
  emptyKey?: string;
}) {
  const { t } = useTranslation();
  if (!status) {
    return <Tag>{t(emptyKey)}</Tag>;
  }
  return (
    <Tag color={statusColor(status)}>
      {t(`backup.remoteStatus.${status}`, { defaultValue: status })}
    </Tag>
  );
}

function destinationLabel(dest: BackupDestinationOption): string {
  const label = dest.label?.trim();
  if (label) return label;
  return dest.name;
}

interface RemoteBackupSectionProps {
  summary: RemoteBackupSummary | null;
  destinations: BackupDestinationOption[];
  busy: boolean;
  timeZone: string;
  onSelectDestination: (backendId: number | null) => void | Promise<void>;
  selectingDestination: boolean;
}

export function RemoteBackupSection({
  summary,
  destinations,
  busy,
  timeZone,
  onSelectDestination,
  selectingDestination,
}: RemoteBackupSectionProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const selectValue = useMemo(() => {
    if (summary?.remote_enabled && summary.remote_backend_id != null) {
      return `backend:${summary.remote_backend_id}`;
    }
    return LOCAL_VALUE;
  }, [summary?.remote_enabled, summary?.remote_backend_id]);

  const options = useMemo(() => {
    const local = {
      value: LOCAL_VALUE,
      label: t("backup.destinationLocal"),
    };
    const remotes = destinations.map((dest) => ({
      value: `backend:${dest.id}`,
      label: destinationLabel(dest),
    }));
    return [local, ...remotes];
  }, [destinations, t]);

  const renderDestinationOption = (
    value: string | number | null | undefined,
    label: ReactNode,
  ) => (
    <span className={styles.destinationOption}>
      {value === LOCAL_VALUE ? <HardDrive size={14} /> : <Cloud size={14} />}
      {label}
    </span>
  );

  const onDestinationChange = async (value: string) => {
    if (value === LOCAL_VALUE) {
      await onSelectDestination(null);
      return;
    }
    const matched = /^backend:(\d+)$/.exec(value);
    if (!matched) return;
    const backendId = Number(matched[1]);
    if (!Number.isFinite(backendId)) return;
    const exists = destinations.some((d) => d.id === backendId);
    if (!exists) {
      message.warning(t("backup.destinationMissing"));
      return;
    }
    await onSelectDestination(backendId);
  };

  const last = summary?.last_mirror;

  return (
    <>
      <TabPanelHeader
        icon={<Cloud size={22} />}
        title={t("backup.remoteTitle")}
        description={t("backup.remoteDesc")}
      />
      <section className={styles.section}>
        <div className={styles.remoteCard}>
          <div className={styles.remoteCardMain}>
            <label className={styles.remoteEnableRow}>
              <span>{t("backup.destinationLabel")}</span>
              <Select
                className={styles.destinationSelect}
                value={selectValue}
                disabled={busy || selectingDestination}
                loading={selectingDestination}
                options={options}
                optionRender={(option) =>
                  renderDestinationOption(option.value, option.label)
                }
                labelRender={(option) =>
                  renderDestinationOption(option.value, option.label)
                }
                onChange={(value) => void onDestinationChange(value)}
              />
            </label>
            {selectValue === LOCAL_VALUE ? (
              <span className={styles.remoteHint}>
                {t("backup.destinationLocalHint")}
              </span>
            ) : null}
            {destinations.length === 0 ? (
              <span className={styles.remoteHint}>
                {t("backup.destinationEmptyHint")}{" "}
                <Link to="/admin/backend">
                  {t("backup.destinationGoStorage")}
                </Link>
              </span>
            ) : null}
            {selectValue !== LOCAL_VALUE && last ? (
              <div className={styles.remoteMeta}>
                <span>
                  {t("backup.remoteLastMirror")}:{" "}
                  <MirrorStatusTag status={last.status} />{" "}
                  {formatServerIsoDateTime(last.checked_at, timeZone)}
                </span>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </>
  );
}
