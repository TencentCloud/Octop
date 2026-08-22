/**
 * Typed parser for harness chat stream chunks.
 *
 * The dashboard receives JSON frames over WebSocket (and HITL resume SSE).
 * Each frame is a single JSON object, e.g.
 *
 *   {"type":"token","node":"agent","content":"hi"}
 *
 * ``parseHarnessChunk`` also accepts legacy ``data: …`` SSE lines.
 */

import type { ThreadTaskState } from "../api/modules/octopThreads";

export interface TokenChunk {
  type: "token";
  /** Graph node that produced the chunk (e.g. ``agent``, ``tool``). */
  node: string;
  /** Streamed text fragment. Concatenate with prior tokens of the same node. */
  content: string;
}

export interface ReasoningChunk {
  type: "reasoning";
  content: string;
}

export interface ToolCallChunk {
  type: "tool_call_chunk";
  /** Stable tool-call id from the harness stream (preferred correlation key). */
  id?: string;
  /** Tool name; absent on continuation chunks for the same call. */
  name?: string;
  /** Server-localized label (when provided by Octop gateway). */
  display_name?: string;
  /** Streamed JSON-encoded args fragment. */
  args?: string;
  /** Index inside a multi-tool call sequence. */
  index?: number;
}

export interface ToolResultChunk {
  type: "tool_result";
  node: string;
  /** Tool output messages — opaque to the parser; renderers project to UI. */
  messages: unknown[];
}

export interface StateUpdateChunk {
  type: "state_update";
  node: string;
  data: unknown;
}

export interface StateSnapshotChunk {
  type: "state_snapshot";
  data: unknown;
}

export interface CustomChunk {
  type: "custom";
  data: unknown;
}

export interface UsageChunk {
  type: "usage";
  call_id?: string;
  model?: string;
  node?: string;
  usage: Record<string, unknown>;
}

export interface DoneChunk {
  type: "done";
}

export interface ErrorChunk {
  type: "error";
  message: string;
}

export interface HitlRequiredChunk {
  type: "hitl_required";
  request: Record<string, unknown>;
}

export interface SlashActionChunk {
  type: "slash_action";
  action: string;
  agent_id?: string;
}

export interface AttachmentChunk {
  type: "attachment";
  url?: string;
  preview_url?: string;
  data?: string;
  mime_type?: string;
  kind?: string;
  filename?: string;
}

export interface TaskPlanUpdatedChunk {
  type: "task_plan_updated";
  thread_id: string;
  task_state: ThreadTaskState;
}

export type HarnessChunk =
  | TokenChunk
  | ReasoningChunk
  | ToolCallChunk
  | ToolResultChunk
  | StateUpdateChunk
  | StateSnapshotChunk
  | CustomChunk
  | UsageChunk
  | DoneChunk
  | ErrorChunk
  | HitlRequiredChunk
  | SlashActionChunk
  | AttachmentChunk
  | TaskPlanUpdatedChunk;

/**
 * Parse one ``data: …`` SSE frame line into a typed chunk.
 *
 * Returns ``null`` when:
 *  - the line is not a ``data:`` payload (event/comment/keep-alive frames),
 *  - the payload is empty or whitespace only,
 *  - the JSON is malformed.
 *
 * Unknown ``type`` values pass through as ``{type: "custom", data: <raw>}`` so
 * the renderer can show a debug pill rather than dropping data silently.
 */
export function parseHarnessChunk(line: string): HarnessChunk | null {
  // Tolerate both "data:foo" and "data: foo" (the standard form has a
  // single space, but our backend doesn't insert one — match either).
  const prefix = line.startsWith("data:")
    ? line.startsWith("data: ")
      ? "data: "
      : "data:"
    : null;
  if (prefix === null) return null;
  const payload = line.slice(prefix.length).trim();
  if (!payload) return null;

  let raw: unknown;
  try {
    raw = JSON.parse(payload);
  } catch {
    return null;
  }
  if (raw === null || typeof raw !== "object") return null;

  const obj = raw as Record<string, unknown>;
  const t = obj.type;
  if (typeof t !== "string") return null;

  switch (t) {
    case "token":
      return {
        type: "token",
        node: typeof obj.node === "string" ? obj.node : "agent",
        content: typeof obj.content === "string" ? obj.content : "",
      };
    case "reasoning":
      return {
        type: "reasoning",
        content: typeof obj.content === "string" ? obj.content : "",
      };
    case "usage":
      return {
        type: "usage",
        call_id: typeof obj.call_id === "string" ? obj.call_id : undefined,
        model: typeof obj.model === "string" ? obj.model : undefined,
        node: typeof obj.node === "string" ? obj.node : undefined,
        usage:
          obj.usage &&
          typeof obj.usage === "object" &&
          !Array.isArray(obj.usage)
            ? (obj.usage as Record<string, unknown>)
            : {},
      };
    case "tool_call_chunk":
      return {
        type: "tool_call_chunk",
        id:
          typeof obj.id === "string" && obj.id.trim()
            ? obj.id.trim()
            : undefined,
        name: typeof obj.name === "string" ? obj.name : undefined,
        display_name:
          typeof obj.display_name === "string" && obj.display_name.trim()
            ? obj.display_name.trim()
            : undefined,
        args: typeof obj.args === "string" ? obj.args : undefined,
        index: typeof obj.index === "number" ? obj.index : undefined,
      };
    case "tool_result":
      return {
        type: "tool_result",
        node: typeof obj.node === "string" ? obj.node : "tool",
        messages: Array.isArray(obj.messages) ? obj.messages : [],
      };
    case "state_update":
      return {
        type: "state_update",
        node: typeof obj.node === "string" ? obj.node : "",
        data: obj.data,
      };
    case "state_snapshot":
      return { type: "state_snapshot", data: obj.data };
    case "done":
      return { type: "done" };
    case "error":
      return {
        type: "error",
        message:
          typeof obj.message === "string" ? obj.message : "unknown error",
      };
    case "hitl_required":
      return {
        type: "hitl_required",
        request:
          obj.request &&
          typeof obj.request === "object" &&
          !Array.isArray(obj.request)
            ? (obj.request as Record<string, unknown>)
            : {},
      };
    case "slash_action":
      return {
        type: "slash_action",
        action: typeof obj.action === "string" ? obj.action : "",
        agent_id: typeof obj.agent_id === "string" ? obj.agent_id : undefined,
      };
    case "attachment":
      return {
        type: "attachment",
        url: typeof obj.url === "string" ? obj.url : undefined,
        preview_url:
          typeof obj.preview_url === "string" ? obj.preview_url : undefined,
        data: typeof obj.data === "string" ? obj.data : undefined,
        mime_type:
          typeof obj.mime_type === "string" ? obj.mime_type : undefined,
        kind: typeof obj.kind === "string" ? obj.kind : undefined,
        filename: typeof obj.filename === "string" ? obj.filename : undefined,
      };
    case "task_plan_updated":
      if (
        !obj.task_state ||
        typeof obj.task_state !== "object" ||
        Array.isArray(obj.task_state)
      ) {
        return { type: "custom", data: raw };
      }
      return {
        type: "task_plan_updated",
        thread_id: typeof obj.thread_id === "string" ? obj.thread_id : "",
        task_state: obj.task_state as unknown as ThreadTaskState,
      };
    default:
      // Forward-compatible: keep the unrecognized payload around so
      // a debug toggle can render it instead of dropping it.
      return { type: "custom", data: raw };
  }
}
