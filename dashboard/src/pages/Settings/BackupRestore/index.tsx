import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Checkbox,
  Divider,
  Empty,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Spin,
  Switch,
  Table,
  Upload,
} from "antd";
import { message } from "@/utils/antdMessage";

import type { ColumnsType } from "antd/es/table";
import {
  Archive,
  Download,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  Upload as UploadIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  backupApi,
  type AutoBackupSettings,
  type BackupFileItem,
} from "../../../api/modules/backup";
import { useServiceRestartContext } from "../../../context/ServiceRestartContext";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import styles from "./index.module.less";

const SCHEDULE_DAILY = "cron:0 4 * * *";
const SCHEDULE_WEEKLY = "cron:0 4 * * 0";
const SCHEDULE_12H = "interval:43200";

const PRESET_SCHEDULES = new Set([
  SCHEDULE_DAILY,
  SCHEDULE_WEEKLY,
  SCHEDULE_12H,
]);

function triggerDownload(blob: Blob, filename: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isAutoBackupName(name: string): boolean {
  return name.startsWith("octop-auto-backup-");
}

/** Seconds when the spec is `interval:<n>`, otherwise null. */
function parseIntervalSeconds(spec: string): number | null {
  const matched = /^interval:(\d+)$/.exec(spec.trim());
  return matched ? Number(matched[1]) : null;
}

interface BackupFileCardProps {
  row: BackupFileItem;
  downloading: boolean;
  busy: boolean;
  timeZone: string;
  onDownload: (row: BackupFileItem) => void;
  onRestore: (row: BackupFileItem) => void;
  onDelete: (row: BackupFileItem) => void;
}

function BackupFileCard({
  row,
  downloading,
  busy,
  timeZone,
  onDownload,
  onRestore,
  onDelete,
}: BackupFileCardProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.backupCard}>
      <div className={styles.backupCardName}>
        {row.name}
        <span className={styles.kindBadge}>
          {isAutoBackupName(row.name)
            ? t("backup.autoKindAuto")
            : t("backup.autoKindManual")}
        </span>
      </div>
      <div className={styles.backupCardMeta}>
        <span>
          {t("backup.colSize")}: {formatSize(row.size)}
        </span>
        <span>
          {t("backup.colCreated")}:{" "}
          {formatServerIsoDateTime(row.created_at, timeZone)}
        </span>
        <span>
          {t("backup.colModified")}:{" "}
          {formatServerIsoDateTime(row.modified_at, timeZone)}
        </span>
      </div>
      <div className={styles.backupCardActions}>
        <Button
          size="small"
          icon={<Download size={14} />}
          loading={downloading}
          disabled={busy}
          onClick={() => void onDownload(row)}
        >
          {t("common.download")}
        </Button>
        <Button
          size="small"
          icon={<RotateCcw size={14} />}
          disabled={busy}
          onClick={() => onRestore(row)}
        >
          {t("backup.restoreAction")}
        </Button>
        <Button
          size="small"
          danger
          icon={<Trash2 size={14} />}
          disabled={busy}
          onClick={() => onDelete(row)}
        >
          {t("common.delete")}
        </Button>
      </div>
    </div>
  );
}

export default function BackupRestorePanel() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const serverTimezone = useServerTimezone();
  const { isRestarting } = useServiceRestartContext();
  const [items, setItems] = useState<BackupFileItem[]>([]);
  const [dir, setDir] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoreConfig, setRestoreConfig] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [restoreProgress, setRestoreProgress] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [pendingRestore, setPendingRestore] = useState<BackupFileItem | null>(
    null,
  );
  const [downloading, setDownloading] = useState<string | null>(null);

  const [autoEnabled, setAutoEnabled] = useState(false);
  const [autoSchedule, setAutoSchedule] = useState(SCHEDULE_DAILY);
  const [schedulePreset, setSchedulePreset] = useState<string>(SCHEDULE_DAILY);
  const [autoRetention, setAutoRetention] = useState(7);
  const [autoScheduled, setAutoScheduled] = useState(false);
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [autoRunning, setAutoRunning] = useState(false);

  const busy =
    creating ||
    restoring ||
    uploadPercent !== null ||
    isRestarting ||
    autoSaving ||
    autoRunning;

  const customIntervalSeconds = parseIntervalSeconds(autoSchedule);

  const applyAutoSettings = useCallback((data: AutoBackupSettings) => {
    setAutoEnabled(data.auto_enabled);
    setAutoSchedule(data.schedule);
    setAutoRetention(data.retention_count);
    setAutoScheduled(Boolean(data.scheduled));
    setSchedulePreset(
      PRESET_SCHEDULES.has(data.schedule) ? data.schedule : "custom",
    );
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await backupApi.listBackups();
      setItems(data.items);
      setDir(data.dir);
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(detail || t("backup.listFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const refreshAuto = useCallback(async () => {
    setAutoLoading(true);
    try {
      const data = await backupApi.getAutoSettings();
      applyAutoSettings(data);
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.autoLoadFailed"), t));
    } finally {
      setAutoLoading(false);
    }
  }, [applyAutoSettings, t]);

  useEffect(() => {
    void refresh();
    void refreshAuto();
  }, [refresh, refreshAuto]);

  const onCreate = async () => {
    setCreating(true);
    try {
      await backupApi.createBackup();
      message.success(t("backup.createSuccess"));
      await refresh();
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.createFailed"), t));
    } finally {
      setCreating(false);
    }
  };

  const onSaveAuto = async () => {
    setAutoSaving(true);
    try {
      const data = await backupApi.updateAutoSettings({
        auto_enabled: autoEnabled,
        schedule: autoSchedule.trim() || SCHEDULE_DAILY,
        retention_count: autoRetention,
      });
      applyAutoSettings(data);
      message.success(t("backup.autoSaveSuccess"));
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.autoSaveFailed"), t));
    } finally {
      setAutoSaving(false);
    }
  };

  const onRunAuto = async () => {
    setAutoRunning(true);
    try {
      await backupApi.runAutoBackup();
      message.success(t("backup.autoRunSuccess"));
      await refresh();
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.autoRunFailed"), t));
    } finally {
      setAutoRunning(false);
    }
  };

  const onDownload = async (row: BackupFileItem) => {
    setDownloading(row.name);
    try {
      const blob = await backupApi.downloadBackup(row.name);
      triggerDownload(blob, row.name);
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(detail || t("backup.exportFailed"));
    } finally {
      setDownloading(null);
    }
  };

  const confirmRestore = async () => {
    if (!pendingRestore) return;
    setRestoring(true);
    setRestoreProgress(true);
    try {
      const result = await backupApi.restoreBackup(
        pendingRestore.name,
        restoreConfig,
      );
      message.success(
        t("backup.importSuccess", {
          agents: result.agents,
          files: result.workspace_files,
        }),
      );
      setRestoreOpen(false);
      setPendingRestore(null);
      await refresh();
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.importFailed"), t));
    } finally {
      setRestoreProgress(false);
      setRestoring(false);
    }
  };

  const onDelete = (row: BackupFileItem) => {
    if (busy) return;
    Modal.confirm({
      title: t("backup.deleteConfirmTitle"),
      content: t("backup.deleteConfirmBody", { name: row.name }),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        await backupApi.deleteBackup(row.name);
        message.success(t("backup.deleteSuccess"));
        await refresh();
      },
    });
  };

  const columns: ColumnsType<BackupFileItem> = [
    {
      title: t("backup.colName"),
      dataIndex: "name",
      key: "name",
      ellipsis: true,
    },
    {
      title: t("backup.autoKind"),
      key: "kind",
      width: 100,
      render: (_: unknown, row) =>
        isAutoBackupName(row.name)
          ? t("backup.autoKindAuto")
          : t("backup.autoKindManual"),
    },
    {
      title: t("backup.colSize"),
      dataIndex: "size",
      key: "size",
      width: 100,
      render: (size: number) => formatSize(size),
    },
    {
      title: t("backup.colCreated"),
      dataIndex: "created_at",
      key: "created_at",
      width: 160,
      render: (v: string) => formatServerIsoDateTime(v, serverTimezone),
    },
    {
      title: t("backup.colModified"),
      dataIndex: "modified_at",
      key: "modified_at",
      width: 160,
      render: (v: string) => formatServerIsoDateTime(v, serverTimezone),
    },
    {
      title: t("backup.colActions"),
      key: "actions",
      width: 225,
      render: (_: unknown, row) => (
        <div className={styles.rowActions}>
          <Button
            type="link"
            size="small"
            icon={<Download size={14} />}
            loading={downloading === row.name}
            disabled={busy}
            onClick={() => void onDownload(row)}
          >
            {t("common.download")}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<RotateCcw size={14} />}
            disabled={busy}
            onClick={() => {
              setPendingRestore(row);
              setRestoreOpen(true);
            }}
          >
            {t("backup.restoreAction")}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<Trash2 size={14} />}
            disabled={busy}
            onClick={() => onDelete(row)}
          >
            {t("common.delete")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <TabPanelHeader
        icon={<Archive size={22} />}
        title={t("backup.storedTitle")}
        description={
          <>
            {t("backup.storedDesc")}
            {dir ? (
              <>
                <br />
                <code className={styles.dirPath}>{dir}</code>
              </>
            ) : null}
          </>
        }
      />
      <section className={styles.section}>
        <div className={styles.actions}>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            loading={creating}
            disabled={busy && !creating}
            onClick={() => void onCreate()}
          >
            {t("backup.createButton")}
          </Button>
          <Upload
            accept=".tar.gz,.tgz,application/gzip,application/x-gzip"
            showUploadList={false}
            disabled={busy}
            beforeUpload={(file) => {
              void (async () => {
                setUploadPercent(0);
                try {
                  await backupApi.uploadBackup(file, (p) =>
                    setUploadPercent(p),
                  );
                  setUploadPercent(100);
                  message.success(
                    t("backup.uploadSuccess", { name: file.name }),
                  );
                  await refresh();
                } catch (err: unknown) {
                  const detail =
                    err instanceof Error ? err.message : String(err);
                  message.error(detail || t("backup.uploadFailed"));
                } finally {
                  setUploadPercent(null);
                }
              })();
              return false;
            }}
          >
            <Button icon={<UploadIcon size={14} />} disabled={busy}>
              {t("backup.uploadButton")}
            </Button>
          </Upload>
          <Button
            icon={<RefreshCw size={14} />}
            disabled={busy}
            onClick={() => void refresh()}
          >
            {t("common.refresh")}
          </Button>
        </div>
        {(uploadPercent !== null || restoreProgress) && (
          <div className={styles.progressBlock}>
            {uploadPercent !== null ? (
              <>
                <div className={styles.progressLabel}>
                  {t("backup.uploading", { percent: uploadPercent })}
                </div>
                <Progress percent={uploadPercent} status="active" />
              </>
            ) : (
              <>
                <div className={styles.progressLabel}>
                  {t("backup.restoring")}
                </div>
                <Progress percent={100} status="active" showInfo={false} />
              </>
            )}
          </div>
        )}
        {isMobile ? (
          loading && items.length === 0 ? (
            <div className={styles.cardLoading}>
              <Spin />
            </div>
          ) : items.length === 0 ? (
            <Empty
              className={styles.cardEmpty}
              description={t("backup.emptyList")}
            />
          ) : (
            <Spin spinning={loading} className={styles.cardListSpin}>
              <div className={styles.cardGrid}>
                {items.map((row) => (
                  <BackupFileCard
                    key={row.name}
                    row={row}
                    downloading={downloading === row.name}
                    busy={busy}
                    timeZone={serverTimezone}
                    onDownload={onDownload}
                    onRestore={(item) => {
                      setPendingRestore(item);
                      setRestoreOpen(true);
                    }}
                    onDelete={onDelete}
                  />
                ))}
              </div>
            </Spin>
          )
        ) : (
          <Table
            className={styles.table}
            rowKey="name"
            size="middle"
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={false}
            locale={{ emptyText: t("backup.emptyList") }}
          />
        )}
        <div className={styles.warning}>
          <Archive
            size={14}
            style={{ verticalAlign: "middle", marginRight: 6 }}
          />
          {t("backup.importWarning")}
        </div>
      </section>

      <Divider style={{ margin: "40px 0" }} />

      <TabPanelHeader
        icon={<Archive size={22} />}
        title={t("backup.autoTitle")}
        description={t("backup.autoDesc")}
      />
      <section className={styles.section}>
        <Spin spinning={autoLoading}>
          <div className={styles.autoForm}>
            <label className={styles.autoRow}>
              <span>{t("backup.autoEnabled")}</span>
              <Switch
                className={styles.autoSwitch}
                checked={autoEnabled}
                disabled={busy}
                onChange={setAutoEnabled}
              />
            </label>
            <label className={styles.autoRow}>
              <span>{t("backup.autoSchedule")}</span>
              <Select
                className={styles.autoControl}
                value={schedulePreset}
                disabled={busy}
                options={[
                  {
                    value: SCHEDULE_DAILY,
                    label: t("backup.autoScheduleDaily"),
                  },
                  {
                    value: SCHEDULE_WEEKLY,
                    label: t("backup.autoScheduleWeekly"),
                  },
                  {
                    value: SCHEDULE_12H,
                    label: t("backup.autoSchedule12h"),
                  },
                  {
                    value: "custom",
                    label: t("backup.autoScheduleCustom"),
                  },
                ]}
                onChange={(value) => {
                  setSchedulePreset(value);
                  if (value !== "custom") {
                    setAutoSchedule(value);
                  }
                }}
              />
            </label>
            {schedulePreset === "custom" ? (
              <label className={styles.autoRow}>
                <span />
                <div className={styles.autoControlStack}>
                  <Input
                    value={autoSchedule}
                    disabled={busy}
                    onChange={(e) => setAutoSchedule(e.target.value)}
                    placeholder={SCHEDULE_DAILY}
                  />
                  <span className={styles.autoHint}>
                    {t("backup.autoScheduleHint")}
                  </span>
                  {customIntervalSeconds !== null ? (
                    <span className={styles.autoHint}>
                      {t("backup.autoIntervalPreview", {
                        seconds: customIntervalSeconds,
                        hours: (customIntervalSeconds / 3600).toFixed(1),
                      })}
                    </span>
                  ) : null}
                </div>
              </label>
            ) : null}
            <label className={styles.autoRow}>
              <span>{t("backup.autoRetention")}</span>
              <InputNumber
                className={styles.autoControl}
                min={1}
                max={365}
                value={autoRetention}
                disabled={busy}
                onChange={(v) =>
                  setAutoRetention(typeof v === "number" ? v : 7)
                }
              />
            </label>
            <div className={styles.autoStatus}>
              {autoScheduled
                ? t("backup.autoScheduled")
                : t("backup.autoNotScheduled")}
            </div>
            <div className={styles.actions}>
              <Button
                type="primary"
                loading={autoSaving}
                disabled={busy && !autoSaving}
                onClick={() => void onSaveAuto()}
              >
                {t("backup.autoSave")}
              </Button>
              <Button
                loading={autoRunning}
                disabled={busy && !autoRunning}
                onClick={() => void onRunAuto()}
              >
                {t("backup.autoRunNow")}
              </Button>
            </div>
          </div>
        </Spin>
      </section>

      <Modal
        title={t("backup.importConfirmTitle")}
        open={restoreOpen}
        onCancel={() => {
          if (!restoring) {
            setRestoreOpen(false);
            setPendingRestore(null);
          }
        }}
        onOk={() => void confirmRestore()}
        okText={t("backup.importConfirmOk")}
        cancelText={t("common.cancel")}
        confirmLoading={restoring}
        okButtonProps={{ danger: true, disabled: busy && !restoring }}
        cancelButtonProps={{ disabled: restoring }}
      >
        <p>
          {t("backup.importConfirmBody", { name: pendingRestore?.name ?? "" })}
        </p>
        <div className={styles.checkboxRow}>
          <Checkbox
            checked={restoreConfig}
            disabled={restoring}
            onChange={(e) => setRestoreConfig(e.target.checked)}
          >
            {t("backup.restoreConfig")}
          </Checkbox>
        </div>
      </Modal>
    </>
  );
}
