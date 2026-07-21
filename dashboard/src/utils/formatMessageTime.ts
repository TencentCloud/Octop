/** Epoch-ms helpers shared by chat and memory history views. */

export function resolveMessageTimestampMs(raw: unknown): number {
  if (typeof raw === "number" && raw > 0) {
    return raw;
  }
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return 0;
}

function asDate(input: Date | string | number): Date | null {
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** YYYY-MM-DD in the given timezone (en-CA). */
export function formatServerYmd(
  input: Date | string | number,
  timeZone?: string,
): string {
  const d = asDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function timeZoneOptions(
  timeZone?: string,
): Pick<Intl.DateTimeFormatOptions, "timeZone"> {
  return timeZone ? { timeZone } : {};
}

/** HH:mm (24h) in the given timezone. */
export function formatServerHourMinute(
  input: Date | string | number,
  timeZone?: string,
): string {
  const d = asDate(input);
  if (!d) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const hour = parts.find((p) => p.type === "hour")?.value ?? "00";
  const minute = parts.find((p) => p.type === "minute")?.value ?? "00";
  return `${hour}:${minute}`;
}

/**
 * Calendar days between *then* and *now* in the given timezone
 * (today − then), floored. Positive when *then* is in the past.
 */
export function calendarDaysAgo(
  thenInput: Date | string | number,
  timeZone?: string,
  now: Date = new Date(),
): number {
  const then = asDate(thenInput);
  if (!then) return Number.NaN;
  const todayKey = formatServerYmd(now, timeZone);
  const thenKey = formatServerYmd(then, timeZone);
  const [ty, tm, td] = todayKey.split("-").map(Number);
  const [oy, om, od] = thenKey.split("-").map(Number);
  return Math.floor(
    (Date.UTC(ty, tm - 1, td) - Date.UTC(oy, om - 1, od)) / 86_400_000,
  );
}

export function formatMessageTime(tsMs: number, timeZone?: string): string {
  if (!tsMs || tsMs <= 0) return "";
  const d = new Date(tsMs);
  const now = new Date();
  const tz = timeZoneOptions(timeZone);
  const hhmm = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    ...tz,
  });
  if (formatServerYmd(d, timeZone) === formatServerYmd(now, timeZone)) {
    return hhmm;
  }
  const date = d.toLocaleDateString(undefined, {
    month: "2-digit",
    day: "2-digit",
    ...tz,
  });
  return `${date} ${hhmm}`;
}

const SERVER_DATE_TIME_OPTS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
};

/** Full datetime for thread lists; epoch seconds from the API. */
export function formatServerDateTime(
  epochSec: number,
  timeZone?: string,
): string {
  if (!epochSec) return "—";
  return new Date(epochSec * 1000).toLocaleString(undefined, {
    ...SERVER_DATE_TIME_OPTS,
    ...timeZoneOptions(timeZone),
  });
}

/** Full datetime for ISO-8601 API strings (e.g. backup file timestamps). */
export function formatServerIsoDateTime(
  iso: string,
  timeZone?: string,
): string {
  const trimmed = iso.trim();
  if (!trimmed) return "—";
  const d = new Date(trimmed);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    ...SERVER_DATE_TIME_OPTS,
    ...timeZoneOptions(timeZone),
  });
}
