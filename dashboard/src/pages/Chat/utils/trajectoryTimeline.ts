import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { laneForKind, type TrajectoryLane } from "./trajectoryModel";

export type SwimlaneMode = "sequence" | "duration" | "actual";

export interface SwimlaneSpan {
  id: string;
  lane: TrajectoryLane;
  start: number;
  end: number;
  eventIds: string[];
}

function eventDuration(event: TrajectoryEvent, mode: SwimlaneMode): number {
  if (mode === "sequence") return 1;
  if (mode === "duration") {
    const key = event.kind === "tool" ? "tool_duration_ms" : "llm_duration_ms";
    const raw = event.payload[key];
    return typeof raw === "number" && Number.isFinite(raw) && raw > 0 ? raw : 1;
  }
  return 1;
}

function actualBounds(
  events: TrajectoryEvent[],
  from: number,
  to: number,
): { start: number; end: number } {
  const start = events[from]?.ts ?? 0;
  const next = events[to];
  const end = next != null ? next.ts : (events[to - 1]?.ts ?? start) + 1;
  return { start, end: end > start ? end : start + 1 };
}

export function deriveSwimlaneSpans(
  events: TrajectoryEvent[],
  mode: SwimlaneMode,
): SwimlaneSpan[] {
  if (events.length === 0) return [];

  const spans: SwimlaneSpan[] = [];
  let cursor = 0;
  let groupStart = 0;

  const flush = (until: number) => {
    const slice = events.slice(groupStart, until);
    if (slice.length === 0) return;
    const lane = laneForKind(slice[0].kind);
    let start: number;
    let end: number;
    if (mode === "actual") {
      ({ start, end } = actualBounds(events, groupStart, until));
    } else {
      start = cursor;
      const width = slice.reduce(
        (sum, event) => sum + eventDuration(event, mode),
        0,
      );
      end = start + width;
      cursor = end;
    }
    spans.push({
      id: slice.map((event) => event.event_id).join(":"),
      lane,
      start,
      end,
      eventIds: slice.map((event) => event.event_id),
    });
  };

  for (let i = 1; i <= events.length; i++) {
    const prevLane = laneForKind(events[groupStart].kind);
    const nextLane = i < events.length ? laneForKind(events[i].kind) : null;
    if (nextLane !== prevLane) {
      flush(i);
      groupStart = i;
    }
  }

  return spans;
}
