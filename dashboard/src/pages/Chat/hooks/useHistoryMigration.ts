import { useCallback, useEffect, useState } from "react";
import {
  octopThreadsApi,
  type HistoryMigrationStatus,
} from "../../../api/modules/octopThreads";

export function useHistoryMigration(
  agentId: string | null | undefined,
  enabled: boolean,
) {
  const [status, setStatus] = useState<HistoryMigrationStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [startFailed, setStartFailed] = useState(false);

  useEffect(() => {
    if (!agentId || !enabled) {
      setStatus(null);
      setStartFailed(false);
      return;
    }
    let stopped = false;
    let timer: number | null = null;
    const pull = async () => {
      let delay = 30_000;
      try {
        const next = await octopThreadsApi.historyMigrationStatus(agentId);
        if (!stopped) setStatus(next);
        if (next.remaining > 0) {
          delay = next.processing || next.agent_busy ? 2000 : 10_000;
        }
      } catch {
        // A later single-flight poll retries without hiding the last known status.
      } finally {
        if (!stopped) timer = window.setTimeout(pull, delay);
      }
    };
    void pull();
    return () => {
      stopped = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [agentId, enabled]);

  const start = useCallback(async () => {
    if (!agentId || starting) return;
    setStarting(true);
    setStartFailed(false);
    try {
      setStatus(await octopThreadsApi.startHistoryMigration(agentId));
    } catch {
      setStartFailed(true);
    } finally {
      setStarting(false);
    }
  }, [agentId, starting]);

  return {
    status,
    visible: Boolean(status && status.remaining > 0),
    starting,
    startFailed,
    start,
  };
}
