import type {
  TrajectoryEvent,
  TrajectoryKind,
  TrajectoryMetrics,
} from "../../../api/modules/trajectory";

export type TrajectoryLane = "input" | "model" | "tools";

export interface TrajectoryLedgerRow {
  id: string;
  kind: string;
  title: string;
  summary: string;
  requestSeq?: number;
  isError: boolean;
}

const INPUT_KINDS = new Set<string>(["user", "system", "unknown"]);
const MODEL_KINDS = new Set<string>(["assistant", "context", "compacted"]);

export function laneForKind(kind: string): TrajectoryLane {
  if (MODEL_KINDS.has(kind)) return "model";
  if (kind === "tool") return "tools";
  if (INPUT_KINDS.has(kind)) return "input";
  return "input";
}

function titleForEvent(event: TrajectoryEvent): string {
  if (event.kind === "assistant" && event.request_seq != null) {
    return `Request #${event.request_seq}`;
  }
  if (event.kind === "tool") {
    const name = event.payload.name;
    return typeof name === "string" && name ? name : "tool";
  }
  if (event.kind === "context") {
    const label = event.payload.label;
    return typeof label === "string" && label ? label : "context";
  }
  if (event.kind === "system") {
    const label = event.payload.label;
    return typeof label === "string" && label ? label : "system";
  }
  return event.kind;
}

export function toLedgerRow(event: TrajectoryEvent): TrajectoryLedgerRow {
  const row: TrajectoryLedgerRow = {
    id: event.event_id,
    kind: event.kind,
    title: titleForEvent(event),
    summary: event.summary,
    isError: event.is_error,
  };
  if (event.request_seq != null) {
    row.requestSeq = event.request_seq;
  }
  return row;
}

export function filterRows(
  rows: TrajectoryLedgerRow[],
  query: string,
): TrajectoryLedgerRow[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) => {
    return (
      row.title.toLowerCase().includes(needle) ||
      row.summary.toLowerCase().includes(needle) ||
      row.kind.toLowerCase().includes(needle)
    );
  });
}

export function collapseTurns(events: TrajectoryEvent[]): TrajectoryEvent[][] {
  const groups: TrajectoryEvent[][] = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    const lastTurn = last?.[0]?.turn_id;
    if (last && event.turn_id && lastTurn && event.turn_id === lastTurn) {
      last.push(event);
    } else {
      groups.push([event]);
    }
  }
  return groups;
}

export function collapseCalls(events: TrajectoryEvent[]): TrajectoryEvent[][] {
  const groups: TrajectoryEvent[][] = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    if (event.kind === "tool" && last?.[0]?.kind === "tool") {
      last.push(event);
    } else {
      groups.push([event]);
    }
  }
  return groups;
}

const METRIC_KEYS: (keyof TrajectoryMetrics)[] = [
  "turns",
  "steps",
  "llm_duration_ms",
  "tool_duration_ms",
  "ttft_avg_ms",
  "tok_per_s",
  "cache_hit_ratio",
  "input_tokens",
  "output_tokens",
  "cache_read_tokens",
];

export interface VisibleMetric {
  key: keyof TrajectoryMetrics;
  value: number;
}

export function visibleMetrics(metrics: TrajectoryMetrics): VisibleMetric[] {
  const entries: VisibleMetric[] = [];
  for (const key of METRIC_KEYS) {
    const value = metrics[key];
    if (value != null) {
      entries.push({ key, value });
    }
  }
  return entries;
}

export type { TrajectoryEvent, TrajectoryKind, TrajectoryMetrics };
