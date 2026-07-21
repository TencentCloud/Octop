import { Dropdown, Switch, Tag, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  Pencil,
  Play,
  Trash2,
  MoreHorizontal,
  Clock,
  AlertCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CronJobSpecOutput } from "../../../../api/types";
import styles from "../index.module.less";
import {
  CHANNEL_ICONS,
  CHANNEL_LABEL_KEYS,
  getChannelColor,
} from "../../Channels/components/constants";
import {
  channelFromSessionKey,
  extractPromptFromJob,
  formatCronTimestamp,
} from "../cronDisplay";

type CronJob = CronJobSpecOutput;

// Accent color per status
const ENABLED_ACCENT = "#22c55e";
const DISABLED_ACCENT = "#8c8c8c";

interface CronJobCardProps {
  job: CronJob;
  timeZone: string;
  onToggleEnabled: (job: CronJob) => void;
  onExecuteNow: (job: CronJob) => void;
  onEdit: (job: CronJob) => void;
  onDelete: (jobId: string) => void;
}

export function CronJobCard({
  job,
  timeZone,
  onToggleEnabled,
  onExecuteNow,
  onEdit,
  onDelete,
}: CronJobCardProps) {
  const { t } = useTranslation();
  const meta = (job.meta as Record<string, unknown> | undefined) ?? {};
  const sessionKey =
    typeof meta.octop_session_key === "string" ? meta.octop_session_key : "";
  const channel = sessionKey
    ? channelFromSessionKey(sessionKey)
    : Array.isArray(job.dispatch?.channel)
    ? job.dispatch.channel[0]
    : job.dispatch?.channel || "dashboard";
  const icon = CHANNEL_ICONS[channel as keyof typeof CHANNEL_ICONS];
  const label = CHANNEL_LABEL_KEYS[channel as keyof typeof CHANNEL_LABEL_KEYS]
    ? t(CHANNEL_LABEL_KEYS[channel as keyof typeof CHANNEL_LABEL_KEYS])
    : channel;
  const prompt = extractPromptFromJob(job);

  const lastStatus =
    typeof meta.octop_last_status === "string" ? meta.octop_last_status : null;
  const lastError =
    typeof meta.octop_last_error === "string" ? meta.octop_last_error : null;
  const lastRunAt =
    typeof meta.octop_last_run_at === "number" ? meta.octop_last_run_at : null;

  const accent = job.enabled ? ENABLED_ACCENT : DISABLED_ACCENT;
  const channelColor = getChannelColor(channel);

  const taskType = job.task_type === "text" ? "text" : "agent";

  const moreMenuItems: MenuProps["items"] = [
    {
      key: "edit",
      label: t("common.edit"),
      icon: <Pencil size={13} />,
      disabled: job.enabled,
      onClick: () => onEdit(job),
    },
    {
      key: "delete",
      label: t("common.delete"),
      icon: <Trash2 size={13} />,
      disabled: job.enabled,
      danger: true,
      onClick: () => onDelete(job.id),
    },
  ];

  return (
    <div
      className={styles.cronCard}
      style={{ "--cron-accent": accent } as React.CSSProperties}
    >
      {/* Accent top bar — channel brand color */}
      <div
        className={styles.cronCardAccent}
        style={{
          background: channelColor,
          opacity: job.enabled ? 1 : 0.4,
        }}
      />

      {/* Header */}
      <div className={styles.cronCardHeader}>
        {/* Channel icon box */}
        <Tooltip title={label}>
          <div
            className={styles.cronCardIcon}
            style={{ color: accent, background: `${accent}1a` }}
          >
            {icon ? (
              <img src={icon} alt={label} style={{ width: 22, height: 22 }} />
            ) : (
              <Clock size={22} />
            )}
          </div>
        </Tooltip>

        {/* Title block */}
        <div className={styles.cronCardTitleBlock}>
          <div className={styles.cronCardName}>{job.name || job.id}</div>
          <div className={styles.cronCardId}>
            <span className={styles.cronCardIdLabel}>ID</span>
            <span className={styles.cronCardIdValue}>{job.id}</span>
          </div>
          <div className={styles.cronCardMeta}>
            {/* Status pill */}
            <div
              className={styles.cronCardStatus}
              style={{
                color: accent,
                background: `${accent}1a`,
              }}
            >
              <span
                className={styles.cronCardStatusDot}
                style={{ background: accent }}
              />
              {job.enabled ? t("common.enabled") : t("common.disabled")}
            </div>
            {/* Task type tag */}
            <Tag style={{ fontSize: 11, margin: 0 }}>
              {taskType === "text"
                ? t("cronJobs.form.taskTypeText")
                : t("cronJobs.form.taskTypeAgent")}
            </Tag>
          </div>
        </div>

        {/* Toggle switch */}
        <Switch
          size="small"
          checked={job.enabled}
          onChange={() => onToggleEnabled(job)}
          className={styles.cronCardSwitch}
        />
      </div>

      {/* Prompt / description */}
      <p className={styles.cronCardDesc}>{prompt || "\u00a0"}</p>

      {/* Cron schedule + last run info */}
      <div className={styles.cronCardInfo}>
        <span className={styles.cronCardInfoItem}>
          <Clock size={11} style={{ flexShrink: 0 }} />
          <code className={styles.cronCardCode}>
            {job.schedule?.cron || "—"}
          </code>
        </span>
        {lastRunAt && (
          <span className={styles.cronCardInfoItem}>
            <span className={styles.cronCardInfoLabel}>
              {t("cronJobs.col.lastRunAt")}:
            </span>
            <span>{formatCronTimestamp(lastRunAt, timeZone)}</span>
          </span>
        )}
        {lastStatus && (
          <Tag
            color={
              lastStatus === "ok"
                ? "success"
                : lastStatus === "error"
                ? "error"
                : "default"
            }
            style={{ fontSize: 11, margin: 0 }}
          >
            {lastStatus}
          </Tag>
        )}
      </div>

      {/* Error row */}
      {lastStatus === "error" && lastError && (
        <div className={styles.cronCardErrorWrap}>
          <Tooltip
            title={lastError}
            mouseEnterDelay={0.3}
            overlayStyle={{ maxWidth: 360 }}
          >
            <div className={styles.cronCardError}>
              <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
              <span className={styles.cronCardErrorText}>{lastError}</span>
            </div>
          </Tooltip>
        </div>
      )}

      {/* Footer actions */}
      <div className={styles.cronCardFooter}>
        <Tooltip title={t("common.edit")} mouseEnterDelay={0.5}>
          <button
            type="button"
            className={styles.cronCardEditBtn}
            disabled={job.enabled}
            onClick={() => onEdit(job)}
            aria-label={t("common.edit")}
          >
            <Pencil size={13} />
          </button>
        </Tooltip>

        <Dropdown
          menu={{ items: moreMenuItems }}
          placement="bottomLeft"
          trigger={["click"]}
        >
          <Tooltip title={t("common.more", "更多")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.cronCardEditBtn}
              aria-label={t("common.more", "更多")}
            >
              <MoreHorizontal size={13} />
            </button>
          </Tooltip>
        </Dropdown>

        {/* Primary action button — right-aligned */}
        <button
          type="button"
          className={styles.cronCardRunBtn}
          style={{ color: accent, borderColor: `${accent}55` }}
          onClick={() => onExecuteNow(job)}
        >
          <Play size={13} />
          {t("cronJobs.executeNow")}
        </button>
      </div>
    </div>
  );
}
