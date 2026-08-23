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
    const pull = () => {
      request<{ memory_maintenance?: MemoryMaintenanceStatus | null }>(
        `/agents/${agentId}/status`,
      )
        .then((row) => {
          if (!stop) setStatus(row.memory_maintenance ?? null);
        })
        .catch(() => {});
    };
    pull();
    const timer = setInterval(pull, 2000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [agentId, enabled]);

  const phase = status?.phase ?? "idle";
  return {
    status,
    visible: VISIBLE.has(phase),
    blocking: BLOCKING.has(phase),
  };
}
