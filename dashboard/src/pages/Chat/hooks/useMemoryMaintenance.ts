import { useEffect, useState } from "react";
import { request } from "../../../api/request";

export type MemoryMaintenancePhase =
  | "idle"
  | "queued"
  | "waiting"
  | "backing_up"
  | "deduplicating"
  | "pruning"
  | "compacting"
  | "done"
  | "skipped";

export interface MemoryMaintenanceStatus {
  phase: MemoryMaintenancePhase | string;
  kind?: string;
  percent?: number;
  detail?: string | null;
  file_bytes?: number | null;
  started_at?: number | null;
  updated_at?: number | null;
  skipped_reason?: string | null;
  scanned?: number;
  total?: number;
}

const VISIBLE = new Set([
  "queued",
  "waiting",
  "backing_up",
  "deduplicating",
  "pruning",
  "compacting",
]);
const BLOCKING = new Set([
  "backing_up",
  "deduplicating",
  "pruning",
  "compacting",
]);

export function useMemoryMaintenance(
  agentId: string | null | undefined,
  enabled: boolean,
) {
  const [status, setStatus] = useState<MemoryMaintenanceStatus | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);

  useEffect(() => {
    setStatus(null);
    setConnectionLost(false);
    if (!agentId || !enabled) {
      return;
    }
    let stop = false;
    let timer: number | null = null;
    const pull = async () => {
      const nextDelay = 2000;
      try {
        const row = await request<{
          memory_maintenance?: MemoryMaintenanceStatus | null;
        }>(`/agents/${agentId}/status`);
        const next = row.memory_maintenance ?? null;
        if (!stop) {
          setStatus(next);
          setConnectionLost(false);
        }
      } catch {
        // Keep the last known state; a later single-flight poll can recover.
        if (!stop) setConnectionLost(true);
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
    visible:
      VISIBLE.has(phase) ||
      (status?.kind === "memory_slim" &&
        ["done", "failed", "skipped"].includes(phase)),
    blocking: BLOCKING.has(phase),
    connectionLost,
  };
}
