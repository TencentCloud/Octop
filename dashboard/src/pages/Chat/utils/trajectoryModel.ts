import type {
  TrajectoryEvent,
  TrajectoryKind,
  TrajectoryMetrics,
} from "../../../api/modules/trajectory";

export type TrajectoryLane = "input" | "model" | "tools";

export type TrajectoryKindLabel =
  | "USER"
  | "ASSISTANT"
  | "TOOL"
  | "CONTEXT"
  | "SYSTEM"
  | "COMPACTED"
  | "UNKNOWN";

export interface TrajectoryLedgerRow {
  id: string;
  kind: string;
  kindLabel: TrajectoryKindLabel;
  title: string;
  summary: string;
  /** Single-line primary text shown in the content cell. */
  content: string;
  /** Tool args JSON (or preview) when kind is tool. */
  toolArgs: string | null;
  /** Tool result preview when kind is tool. */
  toolResult: string | null;
  /** ASSISTANT parent that owns a tool burst (DSH “tool call only”). */
  toolCallOnly?: boolean;
  /** DSH collapsed summary row (no kind badge; leading ellipsis). */
  collapsedSummary?: boolean;
  collapsedSummaryKind?: "assistant" | "turn";
  /** Parent assistant/turn head id when this is a collapsed summary row. */
  collapsedParentId?: string;
  requestSeq?: number;
  isError: boolean;
}

/** Match DeepSeek Harness ui-trajectory lanes: Input / Model / Tools. */
const INPUT_KINDS = new Set<string>(["user", "system", "context", "unknown"]);
const MODEL_KINDS = new Set<string>(["assistant", "compacted"]);

export function laneForKind(kind: string): TrajectoryLane {
  if (kind === "tool") return "tools";
  if (MODEL_KINDS.has(kind)) return "model";
  if (INPUT_KINDS.has(kind)) return "input";
  return "input";
}

export function kindLabelFor(kind: string): TrajectoryKindLabel {
  switch (kind) {
    case "user":
      return "USER";
    case "assistant":
      return "ASSISTANT";
    case "tool":
      return "TOOL";
    case "context":
      return "CONTEXT";
    case "system":
      return "SYSTEM";
    case "compacted":
      return "COMPACTED";
    default:
      return "UNKNOWN";
  }
}

function titleForEvent(event: TrajectoryEvent): string {
  if (event.payload.collapsed_summary === true) {
    return payloadString(event.payload, "content") || event.summary || "";
  }
  if (event.kind === "assistant" && event.payload.tool_call_only === true) {
    return event.summary || "(tool call only)";
  }
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

function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function payloadString(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  const value = payload[key];
  if (typeof value === "string" && value.trim()) return value;
  return null;
}

function isMcpTextBlock(
  value: unknown,
): value is { type?: string; text?: unknown } {
  return (
    typeof value === "object" &&
    value != null &&
    ("text" in value || (value as { type?: unknown }).type === "text")
  );
}

function prettyIfJson(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return null;
  }
}

/** Unwrap MCP `[{type,text}]` / JSON strings into the tool's actual return text. */
export function coerceToolResultText(value: unknown): string | null {
  if (value == null) return null;

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const withoutEllipsis = trimmed.endsWith("…")
      ? trimmed.slice(0, -1).trim()
      : trimmed;
    if (withoutEllipsis.startsWith("[") || withoutEllipsis.startsWith("{")) {
      try {
        const nested = coerceToolResultText(JSON.parse(withoutEllipsis));
        if (nested) return nested;
      } catch {
        const match = /"text"\s*:\s*"((?:\\.|[^"\\])*)/.exec(trimmed);
        if (match?.[1] != null) {
          try {
            return JSON.parse(`"${match[1]}"`) as string;
          } catch {
            return match[1]
              .replace(/\\n/g, "\n")
              .replace(/\\"/g, '"')
              .replace(/\\\\/g, "\\");
          }
        }
      }
    }
    return prettyIfJson(trimmed) ?? value;
  }

  if (Array.isArray(value)) {
    if (value.length > 0 && value.every(isMcpTextBlock)) {
      const joined = value
        .map((block) =>
          typeof block.text === "string"
            ? block.text
            : block.text == null
            ? ""
            : JSON.stringify(block.text),
        )
        .filter((part) => part.length > 0)
        .join("\n\n");
      if (!joined) return null;
      return prettyIfJson(joined) ?? joined;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  if (typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

/** Pretty-print tool args for the Payload inspector tab. */
export function coerceToolArgsText(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    return prettyIfJson(trimmed) ?? value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatToolArgs(payload: Record<string, unknown>): string | null {
  const args = payload.args ?? payload.arguments ?? payload.input;
  if (args == null) return null;
  const text = coerceToolArgsText(args);
  return text ? oneLine(text) : null;
}

function formatToolResult(payload: Record<string, unknown>): string | null {
  const text =
    coerceToolResultText(payload.result) ??
    coerceToolResultText(payload.output) ??
    coerceToolResultText(payload.content);
  return text ? oneLine(text) : null;
}

function contentForEvent(event: TrajectoryEvent): string {
  if (event.kind === "tool") {
    return oneLine(event.summary) || titleForEvent(event);
  }
  const content = payloadString(event.payload, "content");
  if (content) return oneLine(content);
  return oneLine(event.summary);
}

export function toLedgerRow(event: TrajectoryEvent): TrajectoryLedgerRow {
  const toolCallOnly =
    event.kind === "assistant" && event.payload.tool_call_only === true;
  const collapsedSummary = event.payload.collapsed_summary === true;
  const collapsedKind = event.payload.collapsed_summary_kind;
  const parentId = event.payload.parent_event_id;
  const row: TrajectoryLedgerRow = {
    id: event.event_id,
    kind: event.kind,
    kindLabel: kindLabelFor(event.kind),
    title: titleForEvent(event),
    summary: event.summary,
    content: contentForEvent(event),
    toolArgs: event.kind === "tool" ? formatToolArgs(event.payload) : null,
    toolResult: event.kind === "tool" ? formatToolResult(event.payload) : null,
    isError: event.is_error,
  };
  if (toolCallOnly) {
    row.toolCallOnly = true;
  }
  if (collapsedSummary) {
    row.collapsedSummary = true;
    if (collapsedKind === "assistant" || collapsedKind === "turn") {
      row.collapsedSummaryKind = collapsedKind;
    }
    if (typeof parentId === "string" && parentId) {
      row.collapsedParentId = parentId;
    }
  }
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
      row.content.toLowerCase().includes(needle) ||
      row.kind.toLowerCase().includes(needle) ||
      row.kindLabel.toLowerCase().includes(needle) ||
      (row.toolArgs?.toLowerCase().includes(needle) ?? false) ||
      (row.toolResult?.toLowerCase().includes(needle) ?? false)
    );
  });
}

export function collapseTurns(events: TrajectoryEvent[]): TrajectoryEvent[][] {
  const groups: TrajectoryEvent[][] = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    if (!last) {
      groups.push([event]);
      continue;
    }
    const lastTurn =
      last.find((row) => row.turn_id)?.turn_id ?? last[0]?.turn_id ?? null;
    if (event.turn_id && lastTurn && event.turn_id === lastTurn) {
      last.push(event);
      continue;
    }
    if (event.turn_id && lastTurn && event.turn_id !== lastTurn) {
      groups.push([event]);
      continue;
    }
    // Harness often omits turn_id — fall back to USER boundaries so Turns
    // collapse still groups a user message with its following context/tools.
    if (event.kind === "user") {
      groups.push([event]);
      continue;
    }
    if (event.turn_id && !lastTurn) {
      groups.push([event]);
      continue;
    }
    last.push(event);
  }
  return groups;
}

/** Fold tool rows under the preceding assistant (DSH “Calls”). Orphan tools drop. */
export function collapseCalls(events: TrajectoryEvent[]): TrajectoryEvent[][] {
  const groups: TrajectoryEvent[][] = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    if (event.kind === "tool") {
      if (last?.[0]?.kind === "assistant") {
        last.push(event);
      }
      continue;
    }
    groups.push([event]);
  }
  return groups;
}

function toolNameOf(event: TrajectoryEvent): string | null {
  const name = event.payload.name;
  return typeof name === "string" && name.trim() ? name.trim() : null;
}

/** Unique tool names in first-seen order (DSH collapsed-call summary). */
export function uniqueToolNames(tools: readonly TrajectoryEvent[]): string[] {
  const names: string[] = [];
  for (const tool of tools) {
    const name = toolNameOf(tool);
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

/**
 * DSH assistant-tool summary body (ellipsis is rendered by the ledger):
 * `5 tool calls · todo_write, bash, glob`
 */
export function formatCollapsedToolCalls(
  count: number,
  names: readonly string[],
): string {
  if (count <= 0) return "";
  const unit = count === 1 ? "tool call" : "tool calls";
  const namePart = names.length > 0 ? ` · ${names.join(", ")}` : "";
  return `${count} ${unit}${namePart}`;
}

/** DSH turn summary body: `13 steps · 44 tool calls`. */
export function formatCollapsedTurn(steps: number, toolCalls: number): string {
  const stepsPart = steps === 1 ? "1 step" : `${steps} steps`;
  const toolsPart = toolCalls === 1 ? "1 tool call" : `${toolCalls} tool calls`;
  return `${stepsPart} · ${toolsPart}`;
}

function collapsedSummaryEvent(
  head: TrajectoryEvent,
  summary: string,
  kind: "assistant" | "turn",
): TrajectoryEvent {
  return {
    event_id: `${head.event_id}__${kind}_summary`,
    thread_id: head.thread_id,
    agent_id: head.agent_id,
    seq: head.seq,
    ts: head.ts,
    kind: "assistant",
    turn_id: head.turn_id,
    request_seq: head.request_seq,
    is_error: false,
    summary,
    payload: {
      collapsed_summary: true,
      collapsed_summary_kind: kind,
      content: summary,
      parent_event_id: head.event_id,
    },
  };
}

/**
 * DSH “Calls”: keep the assistant row, hide following TOOL rows, and insert a
 * separate summary row (`… N tool calls · names`) with no kind badge.
 */
export function collapseCallRows(
  events: TrajectoryEvent[],
  formatSummary: (
    count: number,
    names: readonly string[],
  ) => string = formatCollapsedToolCalls,
  collapsedAssistantIds?: ReadonlySet<string> | null,
): TrajectoryEvent[] {
  const out: TrajectoryEvent[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event == null) continue;
    out.push(event);
    if (event.kind !== "assistant") continue;
    if (
      collapsedAssistantIds != null &&
      !collapsedAssistantIds.has(event.event_id)
    ) {
      continue;
    }

    const tools: TrajectoryEvent[] = [];
    let cursor = index + 1;
    while (cursor < events.length && events[cursor]?.kind === "tool") {
      const tool = events[cursor];
      if (tool) tools.push(tool);
      cursor += 1;
    }
    if (tools.length === 0) continue;

    out.push(
      collapsedSummaryEvent(
        event,
        formatSummary(tools.length, uniqueToolNames(tools)),
        "assistant",
      ),
    );
    index = cursor - 1;
  }
  return out;
}

/**
 * DSH “Turns”: keep the first row of each turn, hide the rest, and insert
 * `… N steps · M tool calls` as a separate summary row.
 */
export function collapseTurnRows(
  events: TrajectoryEvent[],
  formatSummary: (
    steps: number,
    toolCalls: number,
  ) => string = formatCollapsedTurn,
): TrajectoryEvent[] {
  const out: TrajectoryEvent[] = [];
  const groups = collapseTurns(events);
  for (const group of groups) {
    const head = group[0];
    if (head == null) continue;
    if (group.length <= 1) {
      out.push(head);
      continue;
    }
    const rest = group.slice(1);
    const toolCalls = rest.filter((event) => event.kind === "tool").length;
    const requestSeqs = new Set(
      rest
        .map((event) => event.request_seq)
        .filter((value): value is number => value != null),
    );
    const steps =
      requestSeqs.size > 0
        ? requestSeqs.size
        : rest.filter((event) => event.kind !== "tool").length;
    out.push(head);
    out.push(
      collapsedSummaryEvent(head, formatSummary(steps, toolCalls), "turn"),
    );
  }
  return out;
}

/** Assistants that currently own at least one following tool row. */
export function collapsibleAssistantIds(
  events: readonly TrajectoryEvent[],
): string[] {
  const ids: string[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event?.kind === "assistant" && events[index + 1]?.kind === "tool") {
      ids.push(event.event_id);
    }
  }
  return ids;
}

/**
 * Insert a synthetic ASSISTANT “(tool call only)” parent before orphan tool
 * bursts (DSH parity / historical rows recorded before the service fix).
 * Skips when an assistant row already precedes the tools.
 */
export function ensureToolCallParents(
  events: readonly TrajectoryEvent[],
  label = "(tool call only)",
): TrajectoryEvent[] {
  const out: TrajectoryEvent[] = [];
  for (const event of events) {
    if (event.kind === "tool") {
      const prev = out[out.length - 1];
      // One synthetic parent per orphan burst: consecutive tools share it.
      // Skip when an assistant already owns the burst, or when the previous
      // row is already a tool under that parent.
      if (prev == null || (prev.kind !== "assistant" && prev.kind !== "tool")) {
        out.push({
          event_id: `${event.event_id}__tool_call_only`,
          thread_id: event.thread_id,
          agent_id: event.agent_id,
          seq: event.seq,
          ts: event.ts,
          kind: "assistant",
          turn_id: event.turn_id,
          request_seq: event.request_seq,
          is_error: false,
          summary: label,
          payload: { tool_call_only: true, content: "" },
        });
      }
    }
    out.push(event);
  }
  return out;
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

export function formatDurationMs(milliseconds: number): string {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return `${Math.round(milliseconds)}ms`;
  if (milliseconds < 60_000) {
    const seconds = milliseconds / 1000;
    return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
  }
  const minutes = Math.floor(milliseconds / 60_000);
  const seconds = Math.round((milliseconds % 60_000) / 1000);
  return `${minutes}m${String(seconds).padStart(2, "0")}s`;
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
