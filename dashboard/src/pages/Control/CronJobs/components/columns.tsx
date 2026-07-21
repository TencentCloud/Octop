import { Button, Dropdown, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { MenuProps } from "antd";
import type { CronJobSpecOutput } from "../../../../api/types";
import { MoreHorizontal } from "lucide-react";
import { TFunction } from "i18next";
import {
  CHANNEL_ICONS,
  CHANNEL_LABEL_KEYS,
} from "../../Channels/components/constants";
import {
  channelFromSessionKey,
  extractPromptFromJob,
  formatCronTimestamp,
} from "../cronDisplay";

type CronJob = CronJobSpecOutput;

interface ColumnHandlers {
  onDetail: (job: CronJob) => void;
  onToggleEnabled: (job: CronJob) => void;
  onExecuteNow: (job: CronJob) => void;
  onEdit: (job: CronJob) => void;
  onDelete: (jobId: string) => void;
  t: TFunction;
  timeZone: string;
}

function channelLabel(channel: string, t: TFunction): string {
  const key = CHANNEL_LABEL_KEYS[channel as keyof typeof CHANNEL_LABEL_KEYS];
  return key ? t(key) : channel;
}

export const createColumns = (
  handlers: ColumnHandlers,
): ColumnsType<CronJob> => {
  return [
    {
      title: handlers.t("cronJobs.col.id"),
      dataIndex: "id",
      key: "id",
      width: 120,
      fixed: "left",
      ellipsis: true,
      onHeaderCell: () => ({ style: { paddingLeft: 28 } }),
      render: (id: string, record: CronJob) => {
        const meta = (record.meta as Record<string, unknown> | undefined) ?? {};
        const sessionKey =
          typeof meta.octop_session_key === "string"
            ? meta.octop_session_key
            : "";
        const channel = sessionKey
          ? channelFromSessionKey(sessionKey)
          : Array.isArray(record.dispatch?.channel)
          ? record.dispatch.channel[0]
          : record.dispatch?.channel || "dashboard";
        const icon = CHANNEL_ICONS[channel as keyof typeof CHANNEL_ICONS];
        const label = channelLabel(channel, handlers.t);
        return (
          <Tooltip title={id}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                maxWidth: "100%",
                overflow: "hidden",
                cursor: "pointer",
                paddingLeft: 8,
              }}
              onClick={() => handlers.onDetail(record)}
            >
              <Tooltip title={label}>
                {icon ? (
                  <img
                    src={icon}
                    alt={label}
                    style={{ width: 16, height: 16, flexShrink: 0 }}
                  />
                ) : (
                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: 12,
                      color: "var(--fn-text-tertiary)",
                    }}
                  >
                    {label}
                  </span>
                )}
              </Tooltip>
              <span
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  color: "var(--fn-text-secondary)",
                  fontSize: 13,
                  fontFamily: "monospace",
                }}
              >
                {id}
              </span>
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: handlers.t("common.enabled"),
      dataIndex: "enabled",
      key: "enabled",
      width: 100,
      fixed: "left",
      render: (enabled: boolean) => (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
            paddingLeft: 8,
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              backgroundColor: enabled
                ? "var(--fn-color-success)"
                : "var(--fn-border-input)",
            }}
          />
          {enabled
            ? handlers.t("common.enabled")
            : handlers.t("common.disabled")}
        </span>
      ),
    },
    {
      title: handlers.t("cronJobs.col.trigger"),
      dataIndex: ["schedule", "cron"],
      key: "trigger",
      width: 160,
      render: (trigger: string) => (
        <code style={{ fontSize: 12 }}>{trigger || "—"}</code>
      ),
    },
    {
      title: handlers.t("cronJobs.col.taskType"),
      key: "task_type",
      width: 108,
      render: (_: unknown, record: CronJob) => {
        const taskType = record.task_type === "text" ? "text" : "agent";
        return (
          <Tag style={{ fontSize: 11 }}>
            {taskType === "text"
              ? handlers.t("cronJobs.form.taskTypeText")
              : handlers.t("cronJobs.form.taskTypeAgent")}
          </Tag>
        );
      },
    },
    {
      title: handlers.t("cronJobs.col.prompt"),
      key: "prompt",
      width: 220,
      ellipsis: true,
      render: (_: unknown, record: CronJob) => {
        const content = extractPromptFromJob(record);
        if (!content) {
          return <span style={{ color: "var(--fn-text-tertiary)" }}>—</span>;
        }
        return (
          <Tooltip title={content}>
            <span style={{ color: "var(--fn-text-secondary)", fontSize: 13 }}>
              {content}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: handlers.t("cronJobs.col.lastRunAt"),
      key: "last_run_at",
      width: 168,
      render: (_: unknown, record: CronJob) => {
        const meta = (record.meta as Record<string, unknown> | undefined) ?? {};
        const ts = meta.octop_last_run_at;
        return (
          <span style={{ fontSize: 12, color: "var(--fn-text-secondary)" }}>
            {formatCronTimestamp(
              typeof ts === "number" ? ts : null,
              handlers.timeZone,
            )}
          </span>
        );
      },
    },
    {
      title: handlers.t("cronJobs.col.lastStatus"),
      key: "last_status",
      width: 100,
      render: (_: unknown, record: CronJob) => {
        const meta = (record.meta as Record<string, unknown> | undefined) ?? {};
        const status = meta.octop_last_status;
        const lastError =
          typeof meta.octop_last_error === "string"
            ? meta.octop_last_error
            : null;
        if (typeof status !== "string" || !status) {
          return <span style={{ color: "var(--fn-text-tertiary)" }}>—</span>;
        }
        const color =
          status === "ok"
            ? "success"
            : status === "error"
            ? "error"
            : "default";
        const tag = (
          <Tag color={color} style={{ fontSize: 11 }}>
            {status}
          </Tag>
        );
        if (status === "error" && lastError) {
          return <Tooltip title={lastError}>{tag}</Tooltip>;
        }
        return tag;
      },
    },
    {
      title: handlers.t("cronJobs.col.freshThread"),
      key: "fresh_thread",
      width: 96,
      render: (_: unknown, record: CronJob) => {
        const meta = (record.meta as Record<string, unknown> | undefined) ?? {};
        const fresh = Boolean(meta.octop_fresh_thread);
        return (
          <Tag style={{ fontSize: 11 }}>
            {fresh
              ? handlers.t("cronJobs.col.freshThreadOn")
              : handlers.t("cronJobs.col.freshThreadOff")}
          </Tag>
        );
      },
    },
    {
      title: handlers.t("cronJobs.action"),
      key: "action",
      width: 200,
      fixed: "right",
      render: (_: unknown, record: CronJob) => {
        const menuItems: MenuProps["items"] = [
          {
            key: "edit",
            label: handlers.t("common.edit"),
            disabled: record.enabled,
            onClick: () => handlers.onEdit(record),
          },
          {
            key: "delete",
            label: handlers.t("common.delete"),
            disabled: record.enabled,
            danger: true,
            onClick: () => handlers.onDelete(record.id),
          },
        ];

        return (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Button
              type="link"
              size="small"
              onClick={() => handlers.onToggleEnabled(record)}
            >
              {record.enabled
                ? handlers.t("common.disable")
                : handlers.t("common.enable")}
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() => handlers.onExecuteNow(record)}
            >
              {handlers.t("cronJobs.executeNow")}
            </Button>
            <Dropdown menu={{ items: menuItems }} placement="bottomRight">
              <Button
                type="text"
                size="small"
                icon={<MoreHorizontal size={14} />}
              />
            </Dropdown>
          </div>
        );
      },
    },
  ];
};
