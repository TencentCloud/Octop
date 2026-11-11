import { Alert, Descriptions, Table, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type {
  MemoryStorageInspection,
  SqliteCountCheck,
} from "../../../api/modules/memoryDashboard";

const milliseconds = (value?: number | null) =>
  value == null ? "—" : `${value.toFixed(2)} ms`;
const size = (value?: number | null) =>
  value == null ? "—" : `${(value / 1024).toFixed(1)} KB`;

export default function SqliteStorageDetails({
  inspection,
  before,
}: {
  inspection: MemoryStorageInspection;
  before?: MemoryStorageInspection;
}) {
  const { t } = useTranslation();
  const countValue = (row?: SqliteCountCheck) =>
    !row
      ? "—"
      : row.status === "ok"
      ? row.rows
      : t(`memory.storage.count_${row.status}`);
  const counts = (rows: SqliteCountCheck[], previous?: SqliteCountCheck[]) => (
    <Table
      size="small"
      rowKey="table"
      pagination={false}
      scroll={{ x: before ? 620 : 420 }}
      dataSource={rows}
      columns={[
        {
          title: t("memory.storage.dataCategory"),
          dataIndex: "table",
          render: (name: string) => t(`memory.storage.tables.${name}`),
        },
        ...(before
          ? [
              {
                title: t("memory.storage.countBefore"),
                key: "before",
                render: (_: unknown, row: SqliteCountCheck) =>
                  countValue(
                    previous?.find((item) => item.table === row.table),
                  ),
              },
            ]
          : []),
        {
          title: t(
            before
              ? "memory.storage.countAfter"
              : "memory.storage.namespaceRows",
          ),
          key: "rows",
          render: (_: unknown, row: SqliteCountCheck) => countValue(row),
        },
        ...(before
          ? [
              {
                title: t("memory.storage.countChange"),
                key: "change",
                render: (_: unknown, row: SqliteCountCheck) => {
                  const old = previous?.find(
                    (item) => item.table === row.table,
                  );
                  if (old?.rows == null || row.rows == null) return "—";
                  const delta = row.rows - old.rows;
                  return delta > 0 ? `+${delta}` : String(delta);
                },
              },
            ]
          : []),
        {
          title: t("memory.storage.queryDuration"),
          dataIndex: "elapsed_ms",
          render: milliseconds,
        },
      ]}
    />
  );
  return (
    <>
      <Typography.Text strong>
        {t(
          before ? "memory.storage.comparison" : "memory.storage.sqliteDetails",
        )}
      </Typography.Text>
      {before ? (
        <Table
          size="small"
          rowKey="key"
          pagination={false}
          scroll={{ x: 420 }}
          dataSource={[
            {
              key: "fileSize",
              before: size(before.file_size),
              after: size(inspection.file_size),
            },
            {
              key: "walSize",
              before: size(before.wal_size),
              after: size(inspection.wal_size),
            },
            {
              key: "reclaimable",
              before: size(before.reclaimable_bytes),
              after: size(inspection.reclaimable_bytes),
            },
            {
              key: "inspectionDuration",
              before: milliseconds(before.elapsed_ms),
              after: milliseconds(inspection.elapsed_ms),
            },
          ]}
          columns={[
            {
              title: t("memory.storage.metric"),
              dataIndex: "key",
              render: (key: string) => t(`memory.storage.${key}`),
            },
            { title: t("memory.storage.countBefore"), dataIndex: "before" },
            { title: t("memory.storage.countAfter"), dataIndex: "after" },
          ]}
        />
      ) : (
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2 }}
          items={[
            {
              key: "total",
              label: t("memory.storage.inspectionDuration"),
              children: milliseconds(inspection.elapsed_ms),
            },
            {
              key: "file",
              label: t("memory.storage.fileCheckDuration"),
              children: milliseconds(inspection.file_check_ms),
            },
          ]}
        />
      )}
      <Typography.Text type="secondary">
        {t("memory.storage.inspectionTimingHint")}
      </Typography.Text>
      <Typography.Text strong>
        {t("memory.storage.memoryCounts")}
      </Typography.Text>
      {counts(inspection.memory_counts || [], before?.memory_counts)}
      <Typography.Text strong>
        {t("memory.storage.checkpointCounts")}
      </Typography.Text>
      {inspection.checkpoints_available === false ? (
        <Alert
          type="info"
          showIcon
          message={t("memory.storage.sharedCheckpointHint")}
        />
      ) : (
        counts(inspection.checkpoint_counts || [], before?.checkpoint_counts)
      )}
      <Typography.Text type="secondary">
        {t("memory.storage.checkpointCountHint")}
      </Typography.Text>
      {before && (
        <Typography.Text type="secondary">
          {t("memory.storage.comparisonHint")}
        </Typography.Text>
      )}
    </>
  );
}
