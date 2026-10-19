/** One-shot (`date:`) schedule helpers. Wall-clock strings are server timezone, not browser local. */

export type OneShotPhase = "pending" | "done" | "failed" | "missed" | "paused";

const ONCE_PREFIX = "date:";

export function isOnceTrigger(trigger: string | null | undefined): boolean {
  return Boolean(trigger?.startsWith(ONCE_PREFIX));
}

export function onceRunAtFromTrigger(trigger: string): string {
  return trigger.slice(ONCE_PREFIX.length);
}

/** Value stored on the job card's schedule field: bare cron expr, or the full spec otherwise. */
export function scheduleFieldFromTrigger(trigger: string): string {
  if (trigger.startsWith("cron:")) return trigger.slice("cron:".length);
  return trigger;
}

function part(parts: Intl.DateTimeFormatPart[], type: string): string {
  return parts.find((item) => item.type === type)?.value ?? "00";
}

/** `YYYY-MM-DDTHH:mm:ss` wall clock in `timeZone`. */
export function formatServerWallClock(date: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  let hour = part(parts, "hour");
  if (hour === "24") hour = "00";
  return `${part(parts, "year")}-${part(parts, "month")}-${part(
    parts,
    "day",
  )}T${hour}:${part(parts, "minute")}:${part(parts, "second")}`;
}

/** Default picker value: one hour ahead, as a server-timezone wall clock. */
export function defaultOnceRunAt(
  timeZone: string,
  now: Date = new Date(),
): string {
  return formatServerWallClock(
    new Date(now.getTime() + 60 * 60 * 1000),
    timeZone,
  );
}

export function isFutureWallClock(
  value: string,
  timeZone: string,
  now: Date = new Date(),
): boolean {
  const normalized = value.trim().replace(" ", "T");
  return normalized > formatServerWallClock(now, timeZone);
}

/** `2026-10-18T09:00:00` → `2026-10-18 09:00`. */
export function formatOnceWallClock(value: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value.trim());
  if (!match) return value.trim();
  return `${match[1]} ${match[2]}`;
}

export function formatTriggerText(
  trigger: string | null | undefined,
  labels: { mail: string; once: string },
): string {
  if (!trigger) return "—";
  if (trigger.startsWith("agently:")) return labels.mail;
  if (trigger.startsWith(ONCE_PREFIX)) {
    return `${labels.once} · ${formatOnceWallClock(
      onceRunAtFromTrigger(trigger),
    )}`;
  }
  return trigger;
}

export function oneShotPhase(
  trigger: string | null | undefined,
  enabled: boolean,
  lastStatus: string | null | undefined,
): OneShotPhase | null {
  if (!isOnceTrigger(trigger)) return null;
  if (enabled) return "pending";
  if (lastStatus === "ok") return "done";
  if (lastStatus === "error") return "failed";
  if (lastStatus === "missed") return "missed";
  return "paused";
}

export function oneShotPhaseLabelKey(phase: OneShotPhase): string {
  switch (phase) {
    case "pending":
      return "cronJobs.oneShotPending";
    case "done":
      return "cronJobs.oneShotDone";
    case "failed":
      return "cronJobs.oneShotFailed";
    case "missed":
      return "cronJobs.oneShotMissed";
    case "paused":
      return "cronJobs.oneShotPaused";
  }
}

export function lastRunStatusTag(
  status: string,
): { color: "success" | "error" | "warning"; labelKey: string } | null {
  if (status === "ok")
    return { color: "success", labelKey: "cronJobs.lastStatusOk" };
  if (status === "error")
    return { color: "error", labelKey: "cronJobs.lastStatusError" };
  if (status === "missed")
    return { color: "warning", labelKey: "cronJobs.lastStatusMissed" };
  return null;
}
