import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { laneForKind, type TrajectoryLane } from "./trajectoryModel";

export type SwimlaneMode = "sequence" | "duration" | "actual";

export interface SwimlaneSpan {
  id: string;
  lane: TrajectoryLane;
  kind: string;
  start: number;
  end: number;
  eventIds: string[];
  isError: boolean;
}

export interface TrajectoryTimeRange {
  start: number;
  end: number;
}

export function orderedRange(a: number, b: number): TrajectoryTimeRange {
  return a <= b ? { start: a, end: b } : { start: b, end: a };
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function trajectoryFocusEventIds(
  spans: readonly SwimlaneSpan[],
  range: TrajectoryTimeRange,
): ReadonlySet<string> {
  const ids = new Set<string>();
  for (const span of spans) {
    if (span.start <= range.end && span.end >= range.start) {
      for (const eventId of span.eventIds) {
        ids.add(eventId);
      }
    }
  }
  return ids;
}

export function zoomDomain(args: {
  fullStart: number;
  fullEnd: number;
  domainStart: number;
  domainEnd: number;
  anchorFraction: number;
  zoomFactor: number;
  minDomain: number;
}): TrajectoryTimeRange {
  const {
    fullStart,
    fullEnd,
    domainStart,
    domainEnd,
    anchorFraction,
    zoomFactor,
    minDomain,
  } = args;
  const fullWidth = fullEnd - fullStart;
  const currentWidth = domainEnd - domainStart;
  const nextWidth = clamp(currentWidth * zoomFactor, minDomain, fullWidth);
  const anchorTime = domainStart + anchorFraction * currentWidth;
  let start = anchorTime - anchorFraction * nextWidth;
  let end = start + nextWidth;
  if (start < fullStart) {
    start = fullStart;
    end = fullStart + nextWidth;
  }
  if (end > fullEnd) {
    end = fullEnd;
    start = fullEnd - nextWidth;
  }
  return { start, end };
}

export function panDomain(args: {
  fullStart: number;
  fullEnd: number;
  domainStart: number;
  domainEnd: number;
  deltaFraction: number;
}): TrajectoryTimeRange {
  const { fullStart, fullEnd, domainStart, domainEnd, deltaFraction } = args;
  const domainWidth = domainEnd - domainStart;
  const delta = deltaFraction * domainWidth;
  let start = domainStart + delta;
  let end = domainEnd + delta;
  if (start < fullStart) {
    end += fullStart - start;
    start = fullStart;
  }
  if (end > fullEnd) {
    start -= end - fullEnd;
    end = fullEnd;
  }
  return { start, end };
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

function actualEnd(events: TrajectoryEvent[], index: number): number {
  const event = events[index];
  const start = event?.ts ?? 0;
  const key = event?.kind === "tool" ? "tool_duration_ms" : "llm_duration_ms";
  const duration = event?.payload[key];
  if (
    typeof duration === "number" &&
    Number.isFinite(duration) &&
    duration > 0
  ) {
    return start + duration;
  }
  const next = events[index + 1];
  if (next != null && next.ts > start) return next.ts;
  return start + 1;
}

/**
 * Project each ledger event into a discrete three-lane span (DSH-style).
 * Consecutive same-lane events stay separate blocks — never merged.
 */
export function deriveSwimlaneSpans(
  events: TrajectoryEvent[],
  mode: SwimlaneMode,
): SwimlaneSpan[] {
  if (events.length === 0) return [];

  if (mode === "actual") {
    return events.map((event, index) => {
      const start = event.ts;
      const end = actualEnd(events, index);
      return {
        id: event.event_id,
        lane: laneForKind(event.kind),
        kind: event.kind,
        start,
        end: end > start ? end : start + 1,
        eventIds: [event.event_id],
        isError: event.is_error,
      };
    });
  }

  let cursor = 0;
  return events.map((event) => {
    const start = cursor;
    const end = start + eventDuration(event, mode);
    cursor = end;
    return {
      id: event.event_id,
      lane: laneForKind(event.kind),
      kind: event.kind,
      start,
      end,
      eventIds: [event.event_id],
      isError: event.is_error,
    };
  });
}
