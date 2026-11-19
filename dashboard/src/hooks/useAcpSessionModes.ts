import { useEffect, useState } from "react";
import { acpApi, type AcpSessionMode } from "../api/modules/acp";

/** Modes the selected underlying agent documents. Empty when it has no catalog. */
export function useAcpSessionModes(
  runner: string | null | undefined,
): AcpSessionMode[] {
  const [modes, setModes] = useState<AcpSessionMode[]>([]);

  useEffect(() => {
    const name = (runner ?? "").trim();
    if (!name) {
      setModes([]);
      return;
    }
    let cancelled = false;
    acpApi
      .sessionModes(name)
      .then((data) => {
        if (!cancelled) setModes(data.modes ?? []);
      })
      .catch(() => {
        if (!cancelled) setModes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [runner]);

  return modes;
}
