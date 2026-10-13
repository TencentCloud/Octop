import { useEffect, useState } from "react";
import { octopSettingsApi } from "../api/modules/settings";

/** Whether tool-approval UI should show (HITL or command-guard require_approval). */
export function useHitlEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void octopSettingsApi
      .hitl()
      .then((data) => {
        if (!cancelled) setEnabled(Boolean(data.show_approval_ui));
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return enabled;
}
