import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { octopCronApi } from "../../../api/modules/cronjob";
import { useAgent } from "../../../context/AgentContext";
import type { CronJobSpecOutput, OctopCronRow } from "../../../api/types";
import { channelFromSessionKey } from "./cronDisplay";
import { presetToCron, cronToPreset } from "./components/constants";
import { message } from "@/utils/antdMessage";

import {
  defaultModelFromForm,
  defaultModelToForm,
} from "../../../utils/modelOptions";

type CronJob = CronJobSpecOutput;

/** Octop-aligned form values for create / edit drawer. */
export interface CronJobFormValues {
  id?: string;
  name: string;
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
    name: row.name?.trim() || promptLabel(row.prompt, row.id),
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
    name: job.name || "",
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
    name: (values.name || "").trim(),
    trigger: resolveCronExpression(values),
    prompt: values.prompt.trim(),
    task_type: values.task_type,
    session_key: values.fresh_thread ? null : values.session_key || null,
    fresh_thread: Boolean(values.fresh_thread),
    enabled: Boolean(values.enabled),
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
  /** Which agent the currently painted `jobs` belong to (may lag activeAgent). */
  const [jobsOwnerId, setJobsOwnerId] = useState<string | null>(null);
  /**
   * Only true on cold start with nothing to paint.
   * Expert switches never flip this — they keep shell + previous list until new data.
   */
  const [loading, setLoading] = useState(false);
  /** Background revalidate / expert switch in flight. */
  const [refreshing, setRefreshing] = useState(false);
  const [cronTimezone, setCronTimezone] = useState("UTC");
  const fetchGenRef = useRef(0);
  const timezoneRef = useRef(cronTimezone);
  timezoneRef.current = cronTimezone;
  const activeAgentRef = useRef(activeAgentId);
  activeAgentRef.current = activeAgentId;
  const jobsOwnerRef = useRef<string | null>(null);
  jobsOwnerRef.current = jobsOwnerId;
  /** Per-agent list cache — instant paint when hopping back to an expert. */
  const jobsCacheRef = useRef(new Map<string, CronJob[]>());

  const writeJobs = useCallback((agentId: string, next: CronJob[]) => {
    jobsCacheRef.current.set(agentId, next);
    if (activeAgentRef.current === agentId) {
      setJobs(next);
      setJobsOwnerId(agentId);
      jobsOwnerRef.current = agentId;
    }
  }, []);

  const patchJobs = useCallback(
    (agentId: string, updater: (prev: CronJob[]) => CronJob[]) => {
      const prev =
        activeAgentRef.current === agentId
          ? undefined
          : jobsCacheRef.current.get(agentId) ?? [];
      if (activeAgentRef.current === agentId) {
        setJobs((live) => {
          const next = updater(live);
          jobsCacheRef.current.set(agentId, next);
          return next;
        });
        setJobsOwnerId(agentId);
        jobsOwnerRef.current = agentId;
      } else {
        jobsCacheRef.current.set(agentId, updater(prev ?? []));
      }
    },
    [],
  );

  useEffect(() => {
    void octopCronApi
      .settings()
      .then((s) => setCronTimezone(s.timezone || "UTC"))
      .catch((error) => {
        console.error("Failed to load cron settings", error);
      });
  }, []);

  // Timezone is display-only — remap without APIs or loading toggles.
  useEffect(() => {
    const agentId = activeAgentRef.current;
    setJobs((prev) => {
      if (prev.length === 0) return prev;
      let changed = false;
      const next = prev.map((job) => {
        if (job.schedule.timezone === cronTimezone) return job;
        changed = true;
        return {
          ...job,
          schedule: { ...job.schedule, timezone: cronTimezone },
        };
      });
      if (changed && agentId) {
        jobsCacheRef.current.set(agentId, next);
      }
      return changed ? next : prev;
    });
  }, [cronTimezone]);

  const fetchJobs = useCallback(
    async (opts?: { soft?: boolean }) => {
      const agentId = activeAgentRef.current;
      if (!agentId) {
        setJobs([]);
        setJobsOwnerId(null);
        jobsOwnerRef.current = null;
        setLoading(false);
        setRefreshing(false);
        return;
      }

      const soft = Boolean(opts?.soft);
      const gen = ++fetchGenRef.current;
      const cached = jobsCacheRef.current.get(agentId);
      const hasCache = cached !== undefined;
      // Keep previous expert's rows as a placeholder so the list chrome
      // never unmounts on the first hop to an unseen expert.
      const hasPlaceholder = jobsOwnerRef.current != null || hasCache;

      if (soft) {
        setLoading(false);
        setRefreshing(true);
      } else if (hasCache) {
        setJobs(cached);
        setJobsOwnerId(agentId);
        jobsOwnerRef.current = agentId;
        setLoading(false);
        setRefreshing(true);
      } else if (hasPlaceholder) {
        setLoading(false);
        setRefreshing(true);
      } else {
        setLoading(true);
        setRefreshing(false);
      }

      try {
        const data = await octopCronApi.list(agentId);
        if (gen !== fetchGenRef.current) return;
        const mapped = (data || []).map((row) =>
          fromOctop(row, timezoneRef.current),
        );
        writeJobs(agentId, mapped);
      } catch (error) {
        if (gen !== fetchGenRef.current) return;
        console.error("Failed to load cron jobs", error);
        message.error(t("cronJobs.loadFailed"));
        if (!hasCache && jobsOwnerRef.current !== agentId) {
          setJobs([]);
          setJobsOwnerId(agentId);
          jobsOwnerRef.current = agentId;
        }
      } finally {
        if (gen === fetchGenRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [t, writeJobs],
  );

  // Expert switch: paint cache immediately, revalidate in background.
  useEffect(() => {
    void fetchJobs({ soft: false });
  }, [activeAgentId, fetchJobs]);

  const createJob = async (values: CronJobFormValues) => {
    if (!activeAgentId) return false;
    try {
      const created = await octopCronApi.create(
        activeAgentId,
        toOctopCreateBody(values),
      );
      const row = fromOctop(created, cronTimezone);
      patchJobs(activeAgentId, (prev) => [row, ...prev]);
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
      name: (values.name || "").trim(),
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
    patchJobs(activeAgentId, (prev) =>
      prev.map((j) => (j.id === jobId ? optimistic : j)),
    );

    try {
      const updated = await octopCronApi.patch(
        activeAgentId,
        jobId,
        toOctopPatchBody(values),
      );
      const row = fromOctop(updated, cronTimezone);
      patchJobs(activeAgentId, (prev) =>
        prev.map((j) => (j.id === jobId ? row : j)),
      );
      message.success(t("cronJobs.updatedSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to update cron job", error);
      if (original) {
        patchJobs(activeAgentId, (prev) =>
          prev.map((j) => (j.id === jobId ? original : j)),
        );
      }
      message.error(t("common.saveFailed"));
      return false;
    }
  };

  const deleteJob = async (jobId: string) => {
    if (!activeAgentId) return false;
    const original = jobs.find((j) => j.id === jobId);
    patchJobs(activeAgentId, (prev) => prev.filter((j) => j.id !== jobId));

    try {
      await octopCronApi.delete(activeAgentId, jobId);
      message.success(t("cronJobs.deletedSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to delete cron job", error);
      if (original) {
        patchJobs(activeAgentId, (prev) => [...prev, original]);
      }
      message.error(t("cronJobs.deleteFailed"));
      return false;
    }
  };

  const toggleEnabled = async (job: CronJob) => {
    if (!activeAgentId) return false;
    const nextEnabled = !job.enabled;
    const optimistic = { ...job, enabled: nextEnabled };
    patchJobs(activeAgentId, (prev) =>
      prev.map((j) => (j.id === job.id ? optimistic : j)),
    );

    try {
      const returned = await octopCronApi.patch(activeAgentId, job.id, {
        enabled: nextEnabled,
      });
      const row = fromOctop(returned, cronTimezone);
      patchJobs(activeAgentId, (prev) =>
        prev.map((j) => (j.id === job.id ? row : j)),
      );
      message.success(nextEnabled ? t("common.enabled") : t("common.disabled"));
      return true;
    } catch (error) {
      console.error("Failed to toggle cron job", error);
      patchJobs(activeAgentId, (prev) =>
        prev.map((j) => (j.id === job.id ? job : j)),
      );
      message.error(t("cronJobs.operationFailed"));
      return false;
    }
  };

  const executeNow = async (jobId: string) => {
    if (!activeAgentId) return false;
    try {
      await octopCronApi.runNow(activeAgentId, jobId);
      await fetchJobs({ soft: true });
      message.success(t("cronJobs.triggeredSuccess"));
      return true;
    } catch (error) {
      console.error("Failed to execute cron job", error);
      message.error(t("cronJobs.executeFailed"));
      return false;
    }
  };

  const listStale =
    Boolean(activeAgentId) &&
    jobsOwnerId != null &&
    jobsOwnerId !== activeAgentId;

  return {
    jobs,
    loading,
    listRefreshing: refreshing,
    listStale,
    cronTimezone,
    activeAgentId,
    createJob,
    updateJob,
    deleteJob,
    toggleEnabled,
    executeNow,
    refetchJobs: (soft = true) => fetchJobs({ soft }),
    jobToFormValues,
  };
}
