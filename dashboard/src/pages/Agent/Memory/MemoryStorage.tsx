import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Descriptions,
  Divider,
  Modal,
  Progress,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";
import {
  memoryDashboardApi,
  type MemoryStorageInspection,
  type MemoryStorageStatus,
} from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { message } from "../../../utils/antdMessage";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./MemorySettings.module.less";
import SqliteStorageDetails from "./SqliteStorageDetails";
import SqliteBackups from "./SqliteBackups";

const terminal = (phase?: string) =>
  !phase || ["done", "failed", "skipped"].includes(phase);
const bytes = (value?: number | null): string => {
  if (value == null) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let n = Math.abs(value),
    i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${value < 0 ? "−" : ""}${n.toFixed(i ? 1 : 0)} ${units[i]}`;
};

export default function MemoryStorage({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [inspection, setInspection] = useState<MemoryStorageInspection | null>(
    null,
  );
  const [state, setState] = useState<MemoryStorageStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const mounted = useRef(false);
  const checkInFlight = useRef(false);
  const startInFlight = useRef(false);
  const revision = useRef(0);
  const job = state?.job;
  const running = !terminal(job?.phase);
  const busy = state?.busy ?? true;

  const check = async (manual = false) => {
    if (checkInFlight.current) return;
    checkInFlight.current = true;
    setChecking(true);
    setError(null);
    try {
      const result = await memoryDashboardApi.checkStorage(agentId);
      if (mounted.current) {
        setInspection(result);
        if (manual) message.success(t("memory.storage.checkComplete"));
      }
    } catch (e) {
      if (mounted.current)
        setError(
          e instanceof Error ? e.message : t("memory.storage.checkFailed"),
        );
    } finally {
      checkInFlight.current = false;
      if (mounted.current) setChecking(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inspectedJob: string | null = null;
    const poll = async () => {
      const currentRevision = revision.current;
      try {
        const next = await memoryDashboardApi.storageMaintenanceStatus(agentId);
        if (
          stopped ||
          currentRevision !== revision.current ||
          startInFlight.current
        )
          return;
        setState(next);
        setConnectionLost(false);
        const key = next.job
          ? `${next.job.job_id}:${next.job.phase}`
          : "initial";
        if (!next.busy && terminal(next.job?.phase) && key !== inspectedJob) {
          inspectedJob = key;
          await check();
        }
      } catch {
        if (!stopped) setConnectionLost(true);
      } finally {
        if (!stopped) timer = setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      stopped = true;
      mounted.current = false;
      if (timer) clearTimeout(timer);
    };
    // The parent keys this component by agentId; polling must not restart on renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const start = async () => {
    if (
      startInFlight.current ||
      busy ||
      !inspection?.maintenance_supported ||
      connectionLost
    )
      return;
    startInFlight.current = true;
    revision.current++;
    setStarting(true);
    setError(null);
    try {
      const next = await memoryDashboardApi.startStorageMaintenance(agentId);
      if (mounted.current) {
        setState(next);
        setConfirm(false);
      }
    } catch (e) {
      if (mounted.current)
        setError(
          e instanceof Error ? e.message : t("memory.storage.startFailed"),
        );
    } finally {
      startInFlight.current = false;
      if (mounted.current) setStarting(false);
    }
  };

  const startRestore = async (backupId: string) => {
    if (busy || starting || startInFlight.current || connectionLost)
      throw new Error(t("memory.storage.hostBusy"));
    startInFlight.current = true;
    revision.current++;
    setStarting(true);
    try {
      const next = await memoryDashboardApi.restoreStorage(agentId, backupId);
      if (mounted.current) setState(next);
    } finally {
      startInFlight.current = false;
      if (mounted.current) setStarting(false);
    }
  };
  const report = job?.report;
  const postgres =
    job?.backend === "postgres" || inspection?.backend === "postgres";
  const pgReport = report?.backend === "postgres" ? report : null;
  const restoreReport =
    report && "operation" in report && report.operation === "restore"
      ? report
      : null;
  const sqliteReport =
    report && report.backend !== "postgres" && !("operation" in report)
      ? report
      : null;
  const preview = inspection?.cleanup_preview;
  const tableLabel = (table: string) =>
    t(`memory.storage.tables.${table}`, { defaultValue: table });
  const elapsed = job
    ? Math.max(
        0,
        Math.floor(
          (running ? Date.now() / 1000 : job.updated_at) - job.started_at,
        ),
      )
    : 0;
  const reduced = sqliteReport
    ? sqliteReport.before.file_bytes +
      sqliteReport.before.wal_bytes -
      sqliteReport.after.file_bytes -
      sqliteReport.after.wal_bytes
    : null;
  const disabled =
    busy ||
    checking ||
    starting ||
    connectionLost ||
    !inspection?.maintenance_supported;

  return (
    <section
      className={styles.storageSection}
      aria-label={t("memory.storage.title")}
    >
      <Divider />
      <Typography.Title level={5}>{t("memory.storage.title")}</Typography.Title>
      <Typography.Paragraph type="secondary">
        {t("memory.storage.description")}
      </Typography.Paragraph>
      <Space wrap>
        <Button
          onClick={() => void check(true)}
          loading={checking}
          disabled={state?.busy === true || starting}
        >
          {t(checking ? "memory.storage.checking" : "memory.storage.check")}
        </Button>
        <Button
          type="primary"
          onClick={() => setConfirm(true)}
          disabled={disabled}
          loading={starting}
        >
          {t("memory.storage.maintain")}
        </Button>
      </Space>
      {inspection && (
        <Typography.Text type="secondary" role="status">
          {t("memory.storage.lastChecked", {
            time: formatServerDateTime(inspection.checked_at, timeZone),
          })}
        </Typography.Text>
      )}
      {error && <Alert type="error" showIcon message={error} />}
      {connectionLost && (
        <Alert
          type="warning"
          showIcon
          message={t("memory.storage.connectionLost")}
        />
      )}
      {state?.busy && !running && (
        <Alert type="info" showIcon message={t("memory.storage.hostBusy")} />
      )}
      {!inspection && !error && !busy && checking && <Spin />}
      {inspection && (
        <>
          <Descriptions
            size="small"
            column={{ xs: 1, sm: 2 }}
            bordered
            items={[
              {
                key: "backend",
                label: t("memory.storage.backend"),
                children: (
                  <Tag>
                    {inspection.backend === "postgres"
                      ? "PostgreSQL"
                      : "SQLite"}
                  </Tag>
                ),
              },
              {
                key: "scope",
                label: t("memory.storage.scope"),
                children: t(
                  inspection.backend === "postgres" &&
                    inspection.scope === "agent"
                    ? "memory.storage.scope_namespace"
                    : `memory.storage.scope_${inspection.scope}`,
                ),
              },
              ...(inspection.backend === "sqlite"
                ? [
                    {
                      key: "size",
                      label: t("memory.storage.fileSize"),
                      children: bytes(inspection.file_size),
                    },
                    {
                      key: "wal",
                      label: t("memory.storage.walSize"),
                      children: bytes(inspection.wal_size),
                    },
                    {
                      key: "free",
                      label: t("memory.storage.reclaimable"),
                      children: bytes(inspection.reclaimable_bytes),
                    },
                    {
                      key: "vacuum",
                      label: t("memory.storage.autoVacuum"),
                      children: t(
                        inspection.auto_vacuum_enabled
                          ? "common.enabled"
                          : "common.disabled",
                      ),
                    },
                  ]
                : []),
            ]}
          />
          {inspection.backend === "sqlite" && (
            <Typography.Text type="secondary">
              {t("memory.storage.estimateHint")}
            </Typography.Text>
          )}
          {inspection.blocked_reason && (
            <Alert
              type="info"
              showIcon
              message={t(`memory.storage.blocked_${inspection.blocked_reason}`)}
            />
          )}
          {inspection.backend === "sqlite" && inspection.memory_counts && (
            <SqliteStorageDetails inspection={inspection} />
          )}
          {inspection.backend === "postgres" && (
            <>
              <Alert
                type="info"
                showIcon
                message={t("memory.storage.postgresHint")}
              />
              {preview && (
                <Alert
                  type="info"
                  showIcon
                  message={t("memory.storage.cleanupPreview", {
                    candidates: preview.candidates,
                    journal: preview.journal,
                  })}
                  description={t("memory.storage.cleanupPolicy", {
                    candidateDays: preview.candidate_days,
                    journalDays: preview.journal_days,
                    limit: preview.limit_per_table,
                  })}
                />
              )}
              <Table
                size="small"
                rowKey="table"
                pagination={false}
                scroll={{ x: 420 }}
                dataSource={inspection.namespace_tables || []}
                columns={[
                  {
                    title: t("memory.storage.dataCategory"),
                    dataIndex: "table",
                    render: tableLabel,
                  },
                  {
                    title: t("memory.storage.namespaceRows"),
                    dataIndex: "rows",
                  },
                  {
                    title: t("memory.storage.rowBytes"),
                    dataIndex: "row_bytes",
                    render: bytes,
                  },
                ]}
              />
              <Typography.Text type="secondary">
                {t("memory.storage.rowBytesHint")}
              </Typography.Text>
            </>
          )}
        </>
      )}
      {job && (
        <div className={styles.storageResult} role="status" aria-live="polite">
          <Space wrap>
            <Typography.Text strong>
              {t(
                job.operation === "restore" && job.phase === "done"
                  ? "memory.storage.restoreDone"
                  : `memory.storage.phase_${job.phase}`,
                {
                  defaultValue: job.phase,
                },
              )}
            </Typography.Text>
            <Typography.Text type="secondary">
              {t("memory.storage.elapsed", { seconds: elapsed })}
            </Typography.Text>
          </Space>
          {running && (
            <>
              <Typography.Paragraph type="secondary">
                {t("memory.storage.runningHint")}
              </Typography.Paragraph>
              {["deduplicating", "cleaning"].includes(job.phase) &&
              job.total != null &&
              job.scanned != null ? (
                <>
                  <Progress
                    percent={
                      job.total > 0
                        ? Math.min(
                            100,
                            Math.round((job.scanned / job.total) * 100),
                          )
                        : 0
                    }
                  />
                  <Typography.Text>
                    {t(
                      postgres
                        ? "memory.storage.cleaningProgress"
                        : "memory.storage.scanned",
                      {
                        scanned: job.scanned,
                        total: job.total,
                      },
                    )}
                  </Typography.Text>
                </>
              ) : (
                <Spin size="small" />
              )}
            </>
          )}
          {job.phase === "failed" && (
            <Alert
              type="error"
              showIcon
              message={job.error || t("memory.storage.startFailed")}
              description={t(
                job.operation === "restore"
                  ? "memory.storage.restoreFailureHint"
                  : postgres
                  ? "memory.storage.pgFailureHint"
                  : "memory.storage.failureHint",
              )}
            />
          )}
          {sqliteReport && (
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2 }}
              items={[
                {
                  key: "before",
                  label: t("memory.storage.before"),
                  children: bytes(
                    sqliteReport.before.file_bytes +
                      sqliteReport.before.wal_bytes,
                  ),
                },
                {
                  key: "after",
                  label: t("memory.storage.after"),
                  children: bytes(
                    sqliteReport.after.file_bytes +
                      sqliteReport.after.wal_bytes,
                  ),
                },
                {
                  key: "reduced",
                  label: t("memory.storage.reduced"),
                  children: bytes(reduced),
                },
                {
                  key: "scanned",
                  label: t("memory.storage.processed"),
                  children: sqliteReport.stats.scanned,
                },
                {
                  key: "backupSize",
                  label: t("memory.storage.backupSize"),
                  children: bytes(sqliteReport.backup_bytes),
                },
              ]}
            />
          )}
          {restoreReport && (
            <Alert
              type="success"
              showIcon
              message={t("memory.storage.restoreApplied")}
              description={t("memory.storage.restoreSafetyHint")}
            />
          )}
          {sqliteReport?.inspection_before && sqliteReport.inspection_after && (
            <SqliteStorageDetails
              inspection={sqliteReport.inspection_after}
              before={sqliteReport.inspection_before}
            />
          )}
          {pgReport && (
            <>
              <Descriptions
                size="small"
                column={{ xs: 1, sm: 2 }}
                items={[
                  {
                    key: "total",
                    label: t("memory.storage.cleanedRows"),
                    children: pgReport.total_deleted,
                  },
                  {
                    key: "candidates",
                    label: t("memory.storage.cleanedCandidates"),
                    children: pgReport.candidates_deleted,
                  },
                  {
                    key: "journal",
                    label: t("memory.storage.cleanedJournal"),
                    children: pgReport.journal_deleted,
                  },
                  {
                    key: "backup",
                    label: t("memory.storage.backupSize"),
                    children: bytes(pgReport.backup_bytes),
                  },
                ]}
              />
              <Alert
                type="success"
                showIcon
                message={t(
                  pgReport.total_deleted
                    ? "memory.storage.pgDone"
                    : "memory.storage.pgNoop",
                )}
                description={t("memory.storage.postgresHint")}
              />
            </>
          )}
          {(report?.backup_path || job.backup_path) && (
            <div>
              <Typography.Text strong>
                {t(
                  job.operation === "restore"
                    ? "memory.storage.safetyBackup"
                    : "memory.storage.backup",
                )}
              </Typography.Text>
              <Typography.Paragraph className={styles.backupPath} copyable>
                {report?.backup_path || job.backup_path}
              </Typography.Paragraph>
              <Typography.Text type="secondary">
                {t(
                  postgres
                    ? "memory.storage.pgBackupHint"
                    : "memory.storage.backupHint",
                )}
              </Typography.Text>
            </div>
          )}
          <Typography.Paragraph type="secondary">
            {t("memory.storage.resultLifetime")}
          </Typography.Paragraph>
        </div>
      )}
      {inspection?.backend === "sqlite" && (
        <SqliteBackups
          key={agentId}
          agentId={agentId}
          refreshKey={inspection.checked_at}
          disabled={disabled}
          onRestore={startRestore}
        />
      )}
      <Modal
        title={t("memory.storage.confirmTitle")}
        open={confirm}
        onCancel={() => setConfirm(false)}
        onOk={() => void start()}
        confirmLoading={starting}
        okButtonProps={{ disabled }}
        okText={t("memory.storage.confirmStart")}
        cancelText={t("common.cancel")}
      >
        <Typography.Paragraph>
          {t(
            postgres
              ? "memory.storage.pgConfirmBody"
              : "memory.storage.confirmBody",
          )}
          {postgres && preview && (
            <>
              <br />
              {t("memory.storage.cleanupPreview", {
                candidates: preview.candidates,
                journal: preview.journal,
              })}
            </>
          )}
        </Typography.Paragraph>
        <Alert
          type="info"
          showIcon
          message={t(
            postgres
              ? "memory.storage.pgBackupHint"
              : "memory.storage.backupHint",
          )}
        />
      </Modal>
    </section>
  );
}
