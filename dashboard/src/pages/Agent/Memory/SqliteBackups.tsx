import { useEffect, useState } from "react";
import { Alert, Button, Modal, Space, Table, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  memoryDashboardApi,
  type SqliteBackup,
} from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";

export default function SqliteBackups({
  agentId,
  refreshKey,
  disabled,
  onRestore,
}: {
  agentId: string;
  refreshKey: number;
  disabled: boolean;
  onRestore: (backupId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const zone = useServerTimezone();
  const [backups, setBackups] = useState<SqliteBackup[]>([]);
  const [action, setAction] = useState<"restore" | "delete">("restore");
  const [selected, setSelected] = useState<SqliteBackup | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    setLoading(true);
    setError(null);
    void memoryDashboardApi
      .storageBackups(agentId)
      .then((rows) => {
        if (!stopped) setBackups(rows);
      })
      .catch((e) => {
        if (!stopped)
          setError(
            e instanceof Error ? e.message : t("memory.storage.backupsFailed"),
          );
      })
      .finally(() => {
        if (!stopped) setLoading(false);
      });
    return () => {
      stopped = true;
    };
    // Reload only for a new expert or completed inspection, not render-time translation changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, refreshKey]);
  return (
    <>
      <Typography.Text strong>
        {t("memory.storage.backupsTitle")}
      </Typography.Text>
      <Typography.Text type="secondary">
        {t("memory.storage.backupsHint")}
      </Typography.Text>
      {error && <Alert type="error" showIcon message={error} />}
      <Table
        size="small"
        loading={loading}
        rowKey="backup_id"
        pagination={{ pageSize: 5, hideOnSinglePage: true }}
        scroll={{ x: 640 }}
        dataSource={backups}
        locale={{ emptyText: t("memory.storage.noBackups") }}
        columns={[
          {
            title: t("memory.storage.backupTime"),
            key: "time",
            render: (_: unknown, row: SqliteBackup) =>
              formatServerDateTime(row.created_at, zone),
          },
          {
            title: t("memory.storage.backupKind"),
            dataIndex: "kind",
            render: (kind: string) => t(`memory.storage.${kind}`),
          },
          {
            title: t("memory.storage.backupSize"),
            dataIndex: "size_bytes",
            render: (value: number) => `${(value / 1048576).toFixed(2)} MB`,
          },
          {
            title: t("memory.storage.backupFile"),
            dataIndex: "backup_id",
            ellipsis: true,
          },
          {
            title: t("memory.storage.restoreAction"),
            key: "restore",
            render: (_: unknown, row: SqliteBackup) => (
              <Space>
                <Button
                  disabled={disabled || submitting || loading}
                  onClick={() => {
                    setError(null);
                    setAction("restore");
                    setSelected(row);
                  }}
                >
                  {t("memory.storage.restoreThis")}
                </Button>
                <Button
                  danger
                  disabled={disabled || submitting || loading}
                  onClick={() => {
                    setError(null);
                    setAction("delete");
                    setSelected(row);
                  }}
                >
                  {t("memory.storage.deleteBackup")}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        open={!!selected}
        title={t(
          `memory.storage.${
            action === "delete" ? "deleteBackupTitle" : "restoreTitle"
          }`,
        )}
        onCancel={() => {
          if (!submitting) setSelected(null);
        }}
        confirmLoading={submitting}
        okButtonProps={{ disabled, danger: action === "delete" }}
        cancelButtonProps={{ disabled: submitting }}
        closable={!submitting}
        maskClosable={!submitting}
        okText={t(
          `memory.storage.${
            action === "delete" ? "deleteBackupConfirm" : "restoreConfirm"
          }`,
        )}
        cancelText={t("common.cancel")}
        onOk={async () => {
          if (!selected || disabled || submitting) return;
          setSubmitting(true);
          try {
            if (action === "delete") {
              await memoryDashboardApi.deleteStorageBackup(
                agentId,
                selected.backup_id,
              );
              setBackups((rows) =>
                rows.filter((row) => row.backup_id !== selected.backup_id),
              );
            } else {
              await onRestore(selected.backup_id);
            }
            setSelected(null);
          } catch (e) {
            setError(
              e instanceof Error
                ? e.message
                : t(
                    `memory.storage.${
                      action === "delete"
                        ? "deleteBackupFailed"
                        : "restoreFailed"
                    }`,
                  ),
            );
          } finally {
            setSubmitting(false);
          }
        }}
      >
        <Typography.Paragraph>
          {selected && formatServerDateTime(selected.created_at, zone)}
        </Typography.Paragraph>
        <Typography.Paragraph style={{ overflowWrap: "anywhere" }}>
          {selected?.backup_id}
        </Typography.Paragraph>
        {action === "delete" ? (
          <Alert
            type="warning"
            showIcon
            message={t("memory.storage.deleteBackupWarning")}
          />
        ) : (
          <>
            <Alert
              type="warning"
              showIcon
              message={t("memory.storage.restoreWarning")}
              description={t("memory.storage.restoreScopeHint")}
            />
            <Typography.Paragraph>
              {t("memory.storage.restoreSafetyHint")}
            </Typography.Paragraph>
          </>
        )}
        {error && <Alert type="error" message={error} />}
      </Modal>
    </>
  );
}
