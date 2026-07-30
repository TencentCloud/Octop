export const TIMEZONE_OPTIONS = [
  { value: "UTC", label: "UTC" },
  { value: "Asia/Shanghai", label: "Asia/Shanghai (UTC+8)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (UTC+9)" },
  { value: "Asia/Seoul", label: "Asia/Seoul (UTC+9)" },
  { value: "Asia/Hong_Kong", label: "Asia/Hong_Kong (UTC+8)" },
  { value: "Asia/Singapore", label: "Asia/Singapore (UTC+8)" },
  { value: "Asia/Dubai", label: "Asia/Dubai (UTC+4)" },
  { value: "Europe/London", label: "Europe/London (UTC+0)" },
  { value: "Europe/Paris", label: "Europe/Paris (UTC+1)" },
  { value: "Europe/Berlin", label: "Europe/Berlin (UTC+1)" },
  { value: "Europe/Moscow", label: "Europe/Moscow (UTC+3)" },
  { value: "America/New_York", label: "America/New_York (UTC-5)" },
  { value: "America/Chicago", label: "America/Chicago (UTC-6)" },
  { value: "America/Denver", label: "America/Denver (UTC-7)" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles (UTC-8)" },
  { value: "America/Toronto", label: "America/Toronto (UTC-5)" },
  { value: "Australia/Sydney", label: "Australia/Sydney (UTC+10)" },
  { value: "Australia/Melbourne", label: "Australia/Melbourne (UTC+10)" },
  { value: "Pacific/Auckland", label: "Pacific/Auckland (UTC+12)" },
];

export const DEFAULT_FORM_VALUES = {
  enabled: false,
  schedule: {
    type: "cron" as const,
    timezone: "UTC",
  },
  _scheduleMode: "preset" as const,
  _preset: "daily_9am" as const,
  task_type: "agent" as const,
  dispatch: {
    type: "channel" as const,
    channel: "dashboard",
    target: {
      user_id: "",
      session_id: "",
    },
    mode: "final" as const,
  },
  runtime: {
    max_concurrency: 1,
    timeout_seconds: 120,
    misfire_grace_seconds: 60,
  },
};

/** Form defaults with server-configured cron timezone. */
export function buildDefaultFormValues(timezone: string) {
  return {
    enabled: false,
    schedule: {
      type: "cron" as const,
      timezone,
    },
    _scheduleMode: "preset" as const,
    _preset: "daily_9am" as const,
    prompt: "",
    task_type: "text" as const,
    model: undefined,
    fresh_thread: false,
    session_key: undefined,
    mcp_servers: [],
  };
}

export interface SchedulePreset {
  value: string;
  cron: string;
  labelKey: string;
}

export const SCHEDULE_PRESET_CUSTOM = "custom";

export const SCHEDULE_PRESETS: SchedulePreset[] = [
  {
    value: "every_5min",
    cron: "*/5 * * * *",
    labelKey: "cronJobs.preset.every5min",
  },
  {
    value: "every_10min",
    cron: "*/10 * * * *",
    labelKey: "cronJobs.preset.every10min",
  },
  {
    value: "every_30min",
    cron: "*/30 * * * *",
    labelKey: "cronJobs.preset.every30min",
  },
  {
    value: "every_hour",
    cron: "0 * * * *",
    labelKey: "cronJobs.preset.everyHour",
  },
  {
    value: "every_2hours",
    cron: "0 */2 * * *",
    labelKey: "cronJobs.preset.every2hours",
  },
  {
    value: "daily_9am",
    cron: "0 9 * * *",
    labelKey: "cronJobs.preset.daily9am",
  },
  {
    value: "daily_8pm",
    cron: "0 20 * * *",
    labelKey: "cronJobs.preset.daily8pm",
  },
  {
    value: "weekday_9am",
    cron: "0 9 * * 1-5",
    labelKey: "cronJobs.preset.weekday9am",
  },
  {
    value: "weekly_mon_9am",
    cron: "0 9 * * 1",
    labelKey: "cronJobs.preset.weeklyMon9am",
  },
  {
    value: "monthly_1st_9am",
    cron: "0 9 1 * *",
    labelKey: "cronJobs.preset.monthly1st9am",
  },
];

export function presetToCron(presetValue: string): string | null {
  const preset = SCHEDULE_PRESETS.find((p) => p.value === presetValue);
  return preset ? preset.cron : null;
}

export function cronToPreset(cron: string): string | null {
  const normalized = cron.replace(/\s+/g, " ").trim();
  const preset = SCHEDULE_PRESETS.find((p) => p.cron === normalized);
  return preset ? preset.value : null;
}
