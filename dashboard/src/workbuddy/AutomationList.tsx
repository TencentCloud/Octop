import { Fragment, useState } from "react";
import { Dropdown, Switch, Tooltip } from "antd";
import {
  ChevronDown,
  MoreHorizontal,
  Pencil,
  Play,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CronJobSpecOutput } from "../api/types";
import {
  extractPromptFromJob,
  formatCronTimestamp,
} from "../pages/Control/CronJobs/cronDisplay";

type Job = CronJobSpecOutput;

/** 5.5.6 TaskTab/AutomationRow display; all mutations remain owned by useCronJobs. */
export default function AutomationList({
  jobs,
  timeZone,
  disabled,
  onDetail,
  onEdit,
  onExecuteNow,
  onToggleEnabled,
  onDelete,
}: {
  jobs: Job[];
  timeZone: string;
  disabled: boolean;
  onDetail: (job: Job) => void;
  onEdit: (job: Job) => void;
  onExecuteNow: (job: Job) => void;
  onToggleEnabled: (job: Job) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState<Set<boolean>>(new Set());
  return (
    <div className="atm-task-list wb-automation-list">
      {[true, false].map((enabled) => {
        const items = jobs.filter((job) => (job.enabled === true) === enabled);
        if (!items.length) return null;
        const isCollapsed = collapsed.has(enabled);
        return (
          <Fragment key={String(enabled)}>
            <button
              type="button"
              className="atm-task-group-label"
              aria-expanded={!isCollapsed}
              onClick={() =>
                setCollapsed((current) => {
                  const next = new Set(current);
                  if (next.has(enabled)) next.delete(enabled);
                  else next.add(enabled);
                  return next;
                })
              }
            >
              {t(enabled ? "common.enabled" : "common.disabled")} (
              {items.length})
              <span
                className={`atm-records-group-chevron${
                  isCollapsed ? " atm-records-group-chevron--collapsed" : ""
                }`}
              >
                <ChevronDown aria-hidden="true" />
              </span>
            </button>
            {!isCollapsed &&
              items.map((job) => {
                const meta = job.meta as Record<string, unknown> | undefined;
                const lastRun =
                  typeof meta?.octop_last_run_at === "number"
                    ? meta.octop_last_run_at
                    : null;
                const prompt = extractPromptFromJob(job);
                const name = job.name || job.id;
                return (
                  <div className="atm-row wb-automation-row" key={job.id}>
                    <div className="atm-row-left">
                      <div className="atm-row-content">
                        <button
                          type="button"
                          className="atm-row-main automation-workspace__name-button"
                          onClick={() => onDetail(job)}
                          disabled={disabled}
                          title={prompt}
                        >
                          <span className="atm-row-name">{name}</span>
                        </button>
                        <div className="atm-row-meta">
                          <span
                            className="atm-row-schedule"
                            title={`${job.schedule?.cron || "—"} · ${timeZone}`}
                          >
                            {job.schedule?.cron || "—"}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="atm-row-right">
                      <span
                        className="atm-row-right-text"
                        title={t("cronJobs.col.lastRunAt")}
                      >
                        {lastRun
                          ? formatCronTimestamp(lastRun, timeZone)
                          : t(
                              job.enabled
                                ? "common.enabled"
                                : "common.disabled",
                            )}
                      </span>
                      <div className="atm-row-hover-actions">
                        <Tooltip title={t("cronJobs.executeNow")}>
                          <button
                            type="button"
                            className="atm-row-action-btn wb-automation-action"
                            disabled={disabled}
                            aria-label={`${t("cronJobs.executeNow")}: ${name}`}
                            onClick={() => onExecuteNow(job)}
                          >
                            <Play size={16} aria-hidden="true" />
                          </button>
                        </Tooltip>
                        <Dropdown
                          trigger={["click"]}
                          menu={{
                            items: [
                              {
                                key: "edit",
                                label: t("common.edit"),
                                icon: <Pencil size={14} />,
                                disabled: disabled || job.enabled,
                                onClick: () => onEdit(job),
                              },
                              {
                                key: "delete",
                                label: t("common.delete"),
                                icon: <Trash2 size={14} />,
                                danger: true,
                                disabled: disabled || job.enabled,
                                onClick: () => onDelete(job.id),
                              },
                            ],
                          }}
                        >
                          <button
                            type="button"
                            className="atm-row-action-btn wb-automation-action"
                            disabled={disabled}
                            aria-label={`${t("common.more")}: ${name}`}
                          >
                            <MoreHorizontal size={16} aria-hidden="true" />
                          </button>
                        </Dropdown>
                      </div>
                      <Switch
                        size="small"
                        checked={job.enabled}
                        disabled={disabled}
                        aria-label={`${t(
                          job.enabled ? "common.disable" : "common.enable",
                        )}: ${name}`}
                        onChange={() => onToggleEnabled(job)}
                      />
                    </div>
                  </div>
                );
              })}
          </Fragment>
        );
      })}
    </div>
  );
}
