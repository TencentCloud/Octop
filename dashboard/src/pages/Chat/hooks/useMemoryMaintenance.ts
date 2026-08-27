import { useEffect, useState } from "react";
import { request } from "../../../api/request";

export type MemoryMaintenancePhase =
  | "idle"
  | "queued"
  | "pruning"
  | "compacting"
  | "done"
  | "skipped";

export interface MemoryMaintenanceStatus {
  phase: MemoryMaintenancePhase | string;
  percent?: number;
  detail?: string | null;
  file_bytes?: number | null;
  started_at?: number | null;
  updated_at?: number | null;
  skipped_reason?: string | null;
}

const VISIBLE = new Set(["queued", "pruning", "compacting"]);
const BLOCKING = new Set(["pruning", "compacting"]);

export function useMemoryMaintenance(
  agentId: string | null | undefined,
  enabled: boolean,
) {
  const [status, setStatus] = useState<MemoryMaintenanceStatus | null>(null);

  useEffect(() => {
    if (!agentId || !enabled) {
      setStatus(null);
      return;
    }
    let stop = false;
    let timer: number | null = null;
    const pull = async () => {
      let nextDelay = 10_000;
      try {
        const row = await request<{
          memory_maintenance?: MemoryMaintenanceStatus | null;
        }>(`/agents/${agentId}/status`);
        const next = row.memory_maintenance ?? null;
        if (!stop) setStatus(next);
        if (next && VISIBLE.has(next.phase)) nextDelay = 2000;
      } catch {
        // Keep the last known state; a later single-flight poll can recover.
      } finally {
        if (!stop) timer = window.setTimeout(pull, nextDelay);
      }
    };
    void pull();
    return () => {
      stop = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [agentId, enabled]);

  const phase = status?.phase ?? "idle";
  return {
    status,
    visible: VISIBLE.has(phase),
    blocking: BLOCKING.has(phase),
  };
}
