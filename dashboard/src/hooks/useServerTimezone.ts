import { useEffect, useState } from "react";
import { octopSettingsApi } from "../api/modules/settings";

let cachedTimezone: string | null = null;
let inflight: Promise<string> | null = null;

async function fetchServerTimezone(): Promise<string> {
  if (cachedTimezone) return cachedTimezone;
  if (!inflight) {
    inflight = octopSettingsApi
      .timezone()
      .then((settings) => {
        cachedTimezone = settings.timezone?.trim() || "UTC";
        return cachedTimezone;
      })
      .catch(() => {
        cachedTimezone = "UTC";
        return cachedTimezone;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Server timezone from config.json `default_timezone` (via GET /api/settings/timezone). */
export function useServerTimezone(): string {
  const [timezone, setTimezone] = useState(cachedTimezone ?? "UTC");

  useEffect(() => {
    void fetchServerTimezone().then(setTimezone);
  }, []);

  return timezone;
}
