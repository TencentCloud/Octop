import { useEffect, useState } from "react";
import { octopSettingsApi } from "../api/modules/settings";

/** Coalesce Header + Sidebar mounts so first paint hits capabilities once. */
let inFlight: Promise<boolean> | null = null;

async function loadMobileEnabled(): Promise<boolean> {
  if (inFlight) return inFlight;
  inFlight = octopSettingsApi
    .capabilities()
    .then((data) => Boolean(data.mobile?.enabled))
    .catch(() => false)
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useServerCapabilities() {
  const [mobileEnabled, setMobileEnabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void loadMobileEnabled().then((enabled) => {
      if (!cancelled) {
        setMobileEnabled(enabled);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { mobileEnabled, loading };
}
