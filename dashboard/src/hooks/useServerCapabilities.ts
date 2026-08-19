import { useEffect, useState } from "react";
import { octopSettingsApi } from "../api/modules/settings";

export function useServerCapabilities() {
  const [mobileEnabled, setMobileEnabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    octopSettingsApi
      .capabilities()
      .then((data) => {
        if (!cancelled) setMobileEnabled(Boolean(data.mobile?.enabled));
      })
      .catch(() => {
        if (!cancelled) setMobileEnabled(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { mobileEnabled, loading };
}
