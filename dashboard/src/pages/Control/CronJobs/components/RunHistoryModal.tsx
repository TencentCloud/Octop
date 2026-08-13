import { useEffect, useState } from "react";
import { Empty, Modal, Table, Tag, Tooltip, message } from "antd";
import type { TableColumnsType } from "antd";
import { useTranslation } from "react-i18next";
import { octopCronApi } from "../../../../api/modules/cronjob";
import type { OctopCronRun } from "../../../../api/types";
import { formatCronTimestamp } from "../cronDisplay";

const DEFAULT_PAGE_SIZE = 10;

interface RunHistoryModalProps {
  open: boolean;
  agentId: string;
  cronId: string | null;
  jobName?: string;
  timeZone: string;
  onClose: () => void;
}

export function RunHistoryModal({
  open,
  agentId,
  cronId,
  jobName,
  timeZone,
  onClose,
}: RunHistoryModalProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<OctopCronRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    if (!open || !cronId) return;
    let cancelled = false;
    setLoading(true);
    void octopCronApi
      .listRuns(agentId, cronId, page, pageSize)
      .then((result) => {
        if (cancelled) return;
        setItems(result.items);
        setTotal(result.total);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error("Failed to load cron run history", error);
        message.error(t("cronJobs.runHistory.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, cronId, open, page, pageSize, t]);

  useEffect(() => {
    if (!open) {
      setItems([]);
      setPage(1);
      setPageSize(DEFAULT_PAGE_SIZE);
      setTotal(0);
    }
  }, [open]);

  const columns: TableColumnsType<OctopCronRun> = [
    {
      title: t("cronJobs.runHistory.completedAt"),
      dataIndex: "completed_at",
      width: 190,
      render: (value: number) => formatCronTimestamp(value, timeZone),
    },
    {
      title: t("cronJobs.runHistory.status"),
      dataIndex: "status",
      width: 100,
      render: (status: OctopCronRun["status"]) => (
        <Tag color={status === "ok" ? "success" : "error"}>
          {status === "ok"
            ? t("cronJobs.runHistory.succeeded")
            : t("cronJobs.runHistory.failed")}
        </Tag>
      ),
    },
    {
      title: t("cronJobs.runHistory.error"),
      dataIndex: "error",
      ellipsis: true,
      render: (error: string | null) =>
        error ? (
          <Tooltip title={error} placement="topLeft">
            <span>{error}</span>
          </Tooltip>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <Modal
      open={open}
      title={
        jobName
          ? t("cronJobs.runHistory.titleWithName", { name: jobName })
          : t("cronJobs.runHistory.title")
      }
      onCancel={onClose}
      footer={null}
      width={760}
      destroyOnHidden
    >
      <Table<OctopCronRun>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        locale={{
          emptyText: <Empty description={t("cronJobs.runHistory.empty")} />,
        }}
        scroll={{ x: 620, y: 420 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50],
          showTotal: (count) => t("cronJobs.totalItems", { count }),
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPageSize === pageSize ? nextPage : 1);
            setPageSize(nextPageSize);
          },
        }}
      />
    </Modal>
  );
}
