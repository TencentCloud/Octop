import { useState, useEffect, useCallback } from "react";
import { message } from "antd";
import { useTranslation } from "react-i18next";
import { octopCronApi } from "../../../api/modules/cronjob";
import { useAgent } from "../../../context/AgentContext";
import type { CronJobSpecOutput, OctopCronRow } from "../../../api/types";
import { channelFromSessionKey } from "./cronDisplay";
import { presetToCron, cronToPreset } from "./components/constants";
import {
  defaultModelFromForm,
  defaultModelToForm,
} from "../../../utils/modelOptions";

type CronJob = CronJobSpecOutput;

/** Octop-aligned form values for create / edit drawer. */
export interface CronJobFormValues {
  id?: string;
  enabled: boolean;
  schedule: {
    type: "cron";
    cron?: string;
    timezone: string;
  };
  _scheduleMode?: "preset" | "custom";
  _preset?: string;
  prompt: string;
  task_type: "text" | "agent";
  model?: string;
  fresh_thread: boolean;
  session_key?: string | null;
  mcp_servers?: string[];
}

function promptLabel(prompt: string, id: string): string {
  const text = prompt.trim();
  if (!text) return id;
  return text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

function fromOctop(row: OctopCronRow, timezone: string): CronJob {
  const idx = row.trigger.indexOf(":");
  const kind = idx >= 0 ? row.trigger.slice(0, idx) : "";
  const value = idx >= 0 ? row.trigger.slice(idx + 1) : row.trigger;
  const cron = kind === "cron" ? value : row.trigger;
  const channel = channelFromSessionKey(row.session_key);

  return {
    id: row.id,
    name: promptLabel(row.prompt, row.id),
    enabled: row.enabled,
    schedule: {
      type: "cron",
      cron,
      timezone,
    },
    task_type: row.task_type === "text" ? "text" : "agent",
    model: row.model ?? undefined,
    request: {
      input: [
        {
          role: "user",
          content: [{ text: row.prompt || "", type: "text" }],
        },
      ],
    },
    dispatch: {
      type: "channel",
      channel,
      target: {
        user_id: "admin",
        session_id: "default",
      },
      mode: "final",
    },
    meta: {
      orca_agent_id: row.agent_id,
      octop_fresh_thread: row.fresh_thread,
      octop_session_key: row.session_key,
      octop_model: row.model,
      octop_task_type: row.task_type,
      octop_mcp_servers: row.mcp_servers ?? [],
      octop_last_run_at: row.last_run_at,
      octop_last_status: row.last_status,
      octop_last_error: row.last_error,
    },
  };
}

export function jobToFormValues(
  job: CronJob,
  timezone: string,
): CronJobFormValues {
  const meta = (job.meta as Record<string, unknown> | undefined) ?? {};
  const input = job.request?.input;
  let prompt = "";
  if (Array.isArray(input) && input.length > 0) {
    const last = input[input.length - 1] as
      | { content?: Array<{ type: string; text: string }> }
      | undefined;
    const part = last?.content?.find?.((c) => c.type === "text");
    if (part?.text) prompt = part.text;
  }
  const idx = (job.schedule?.cron || "").indexOf(":");
  const cronExpr =
    idx >= 0 && job.schedule?.cron?.startsWith("cron:")
      ? job.schedule.cron.slice(idx + 1)
      : job.schedule?.cron || "";

  const matchedPreset = cronToPreset(cronExpr);
  return {
    id: job.id,
    enabled: Boolean(job.enabled),
    schedule: {
      type: "cron",
      cron: cronExpr,
      timezone,
    },
    prompt,
    task_type: job.task_type === "text" ? "text" : "agent",
    model: defaultModelToForm(
      job.model ??
        (typeof meta.octop_model === "string" ? meta.octop_model : undefined),
    ),
    fresh_thread: Boolean(meta.octop_fresh_thread),
    session_key:
      typeof meta.octop_session_key === "string"
        ? meta.octop_session_key
        : null,
    mcp_servers: Array.isArray(meta.octop_mcp_servers)
      ? (meta.octop_mcp_servers as string[])
      : [],
    _scheduleMode: matchedPreset ? "preset" : "custom",
    _preset: matchedPreset || "daily_9am",
  };
}

function resolveCronExpression(values: CronJobFormValues): string {
  if (values._scheduleMode === "preset" && values._preset) {
    const presetCron = presetToCron(values._preset);
    if (presetCron) return `cron:${presetCron}`;
  }
  const cron = values.schedule?.cron || "";
  return /^(cron|interval|date):/.test(cron) ? cron : `cron:${cron}`;
}

function toOctopCreateBody(values: CronJobFormValues) {
  return {
    trigger: resolveCronExpression(values),
    prompt: values.prompt.trim(),
    task_type: values.task_type,
    session_key: values.session_key || null,
    fresh_thread: Boolean(values.fresh_thread),
    model: defaultModelFromForm(values.model),
    mcp_servers: values.mcp_servers ?? [],
  };
}

function toOctopPatchBody(values: CronJobFormValues) {
  return {
    ...toOctopCreateBody(values),
    enabled: Boolean(values.enabled),
  };
}

export function useCronJobs() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [cronTimezone, setCronTimezone] = useState("UTC");

  useEffect(() => {
    void octopCronApi
      .settings()
      .then((s) => setCronTimezone(s.timezone || "UTC"))
      .catch((error) => {
        console.error("Failed to load cron settings", error);
      });
  }, []);

  const fetchJobs = useCallback(async () => {
    if (!activeAgentId) {
      setJobs([]);
      return;
    }
    setLoading(true);
    try {
      const data = await octopCronApi.list(activeAgentId);
      setJobs((data || []).map((row) => fromOctop(row, cronTimezone)));
    } catch (error) {
      console.error("Failed to load cron jobs", error);
      message.error(t("cronJobs.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [activeAgentId, cronTimezone, t]);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const createJob = async (values: CronJobFormValues) => {
    if (!activeAgentId) return false;
    try {
      const created = await octopCronApi.create(
        activeAgentId,
        toOctopCreateBody(values),
      );
      setJobs((prev) => [fromOctop(created, cronTimezone), ...prev]);
      message.success(t("cronJobs.createdSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to create cron job", error);
      message.error(t("common.saveFailed"));
      return false;
    }
  };

  const updateJob = async (jobId: string, values: CronJobFormValues) => {
    if (!activeAgentId) return false;
    const original = jobs.find((j) => j.id === jobId);
    const optimistic = {
      ...original,
      enabled: values.enabled,
      task_type: values.task_type,
      model: values.model ?? undefined,
      schedule: { ...original?.schedule, cron: values.schedule?.cron },
      request: {
        input: [
          { role: "user", content: [{ text: values.prompt, type: "text" }] },
        ],
      },
      meta: {
        ...(original?.meta as object),
        octop_fresh_thread: values.fresh_thread,
        octop_session_key: values.session_key,
        octop_model: values.model,
      },
    } as CronJob;
    setJobs((prev) => prev.map((j) => (j.id === jobId ? optimistic : j)));

    try {
      const updated = await octopCronApi.patch(
        activeAgentId,
        jobId,
        toOctopPatchBody(values),
      );
      setJobs((prev) =>
        prev.map((j) =>
          j.id === jobId ? fromOctop(updated, cronTimezone) : j,
        ),
      );
      message.success(t("cronJobs.updatedSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to update cron job", error);
      if (original) {
        setJobs((prev) => prev.map((j) => (j.id === jobId ? original : j)));
      }
      message.error(t("common.saveFailed"));
      return false;
    }
  };

  const deleteJob = async (jobId: string) => {
    if (!activeAgentId) return false;
    const original = jobs.find((j) => j.id === jobId);
    setJobs((prev) => prev.filter((j) => j.id !== jobId));

    try {
      await octopCronApi.delete(activeAgentId, jobId);
      message.success(t("cronJobs.deletedSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to delete cron job", error);
      if (original) {
        setJobs((prev) => [...prev, original]);
      }
      message.error(t("cronJobs.deleteFailed"));
      return false;
    }
  };

  const toggleEnabled = async (job: CronJob) => {
    if (!activeAgentId) return false;
    const nextEnabled = !job.enabled;
    const optimistic = { ...job, enabled: nextEnabled };
    setJobs((prev) => prev.map((j) => (j.id === job.id ? optimistic : j)));

    try {
      const returned = await octopCronApi.patch(activeAgentId, job.id, {
        enabled: nextEnabled,
      });
      setJobs((prev) =>
        prev.map((j) =>
          j.id === job.id ? fromOctop(returned, cronTimezone) : j,
        ),
      );
      message.success(nextEnabled ? t("common.enabled") : t("common.disabled"));
      return true;
    } catch (error) {
      console.error("Failed to toggle cron job", error);
      setJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)));
      message.error(t("cronJobs.operationFailed"));
      return false;
    }
  };

  const executeNow = async (jobId: string) => {
    if (!activeAgentId) return false;
    try {
      await octopCronApi.runNow(activeAgentId, jobId);
      await fetchJobs();
      message.success(t("cronJobs.triggeredSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to execute cron job", error);
      message.error(t("cronJobs.executeFailed"));
      return false;
    }
  };

  return {
    jobs,
    loading,
    cronTimezone,
    activeAgentId,
    createJob,
    updateJob,
    deleteJob,
    toggleEnabled,
    executeNow,
    refetchJobs: fetchJobs,
    jobToFormValues,
  };
}
