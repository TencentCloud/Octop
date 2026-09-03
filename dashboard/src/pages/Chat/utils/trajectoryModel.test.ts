import { describe, expect, it } from "vitest";
import type {
  TrajectoryEvent,
  TrajectoryMetrics,
} from "../../../api/modules/trajectory";
import {
  collapseCalls,
  collapseCallRows,
  collapseTurns,
  ensureToolCallParents,
  filterRows,
  formatCollapsedToolCalls,
  formatDurationMs,
  kindLabelFor,
  laneForKind,
  toLedgerRow,
  visibleMetrics,
  coerceToolResultText,
} from "./trajectoryModel";

function event(
  overrides: Partial<TrajectoryEvent> &
    Pick<TrajectoryEvent, "event_id" | "kind">,
): TrajectoryEvent {
  return {
    thread_id: "T1",
    agent_id: "A1",
    seq: 1,
    ts: 1,
    turn_id: null,
    request_seq: null,
    is_error: false,
    summary: "",
    payload: {},
    ...overrides,
  };
}

describe("laneForKind", () => {
  it("maps user and system to the input lane", () => {
    expect(laneForKind("user")).toBe("input");
    expect(laneForKind("system")).toBe("input");
  });

  it("maps assistant and compacted to the model lane", () => {
    expect(laneForKind("assistant")).toBe("model");
    expect(laneForKind("compacted")).toBe("model");
  });

  it("maps context to the input lane (DSH parity)", () => {
    expect(laneForKind("context")).toBe("input");
  });

  it("maps tool to the tools lane", () => {
    expect(laneForKind("tool")).toBe("tools");
  });

  it("maps unknown kinds to the input lane", () => {
    expect(laneForKind("unknown")).toBe("input");
  });
});

describe("toLedgerRow", () => {
  it("copies id, summary, and error flag from the event", () => {
    const row = toLedgerRow(
      event({
        event_id: "e1",
        kind: "user",
        summary: "hello",
        is_error: true,
      }),
    );
    expect(row).toMatchObject({
      id: "e1",
      kind: "user",
      summary: "hello",
      isError: true,
    });
  });

  it("labels assistant rows as Request #N when request_seq is set", () => {
    const row = toLedgerRow(
      event({
        event_id: "a1",
        kind: "assistant",
        request_seq: 3,
        summary: "thinking…",
      }),
    );
    expect(row.title).toBe("Request #3");
    expect(row.requestSeq).toBe(3);
  });

  it("uses the tool name as the row title", () => {
    const row = toLedgerRow(
      event({
        event_id: "t1",
        kind: "tool",
        summary: "tool read_file",
        payload: { name: "read_file" },
      }),
    );
    expect(row.title).toBe("read_file");
  });

  it("unwraps MCP content-block tool results for the ledger", () => {
    const row = toLedgerRow(
      event({
        event_id: "t2",
        kind: "tool",
        summary: "tool list_projects",
        payload: {
          name: "list_projects",
          result: [
            {
              type: "text",
              text: '{\n  "id": "1",\n  "name": "工作"\n}',
            },
          ],
        },
      }),
    );
    expect(row.toolResult).toContain('"name": "工作"');
    expect(row.toolResult).not.toContain('"type": "text"');
  });

  it("omits requestSeq when the event has none", () => {
    const row = toLedgerRow(event({ event_id: "u1", kind: "user" }));
    expect(row.requestSeq).toBeUndefined();
  });
});

describe("coerceToolResultText", () => {
  it("pretty-prints unwrapped MCP text JSON", () => {
    const text = coerceToolResultText([
      { type: "text", text: '{"id":"1","name":"工作"}' },
    ]);
    expect(text).toContain('"name": "工作"');
    expect(text).not.toContain("type");
  });
});

describe("filterRows", () => {
  const rows = [
    {
      id: "1",
      kind: "tool",
      kindLabel: "TOOL" as const,
      title: "read_file",
      summary: "open a.py",
      content: "open a.py",
      toolArgs: null,
      toolResult: null,
      isError: false,
    },
    {
      id: "2",
      kind: "assistant",
      kindLabel: "ASSISTANT" as const,
      title: "Request #1",
      summary: "I'll look at the source",
      content: "I'll look at the source",
      toolArgs: null,
      toolResult: null,
      requestSeq: 1,
      isError: false,
    },
  ];

  it("returns every row when the query is empty or whitespace", () => {
    expect(filterRows(rows, "")).toEqual(rows);
    expect(filterRows(rows, "   ")).toEqual(rows);
  });

  it("matches title, summary, or kind case-insensitively", () => {
    expect(filterRows(rows, "READ").map((row) => row.id)).toEqual(["1"]);
    expect(filterRows(rows, "source")).toHaveLength(1);
    expect(filterRows(rows, "source")[0].id).toBe("2");
    expect(filterRows(rows, "tool").map((row) => row.id)).toEqual(["1"]);
  });

  it("returns no rows when nothing matches", () => {
    expect(filterRows(rows, "xyz")).toEqual([]);
  });
});

describe("visibleMetrics", () => {
  const base: TrajectoryMetrics = {
    turns: 2,
    steps: 5,
    llm_duration_ms: null,
    tool_duration_ms: 40,
    ttft_avg_ms: null,
    tok_per_s: 0,
    cache_hit_ratio: null,
    input_tokens: 10,
    output_tokens: null,
    cache_read_tokens: null,
  };

  it("omits null metric fields and keeps zeros", () => {
    const entries = visibleMetrics(base);
    expect(entries.map((entry) => entry.key)).toEqual([
      "turns",
      "steps",
      "tool_duration_ms",
      "tok_per_s",
      "input_tokens",
    ]);
    expect(entries.find((entry) => entry.key === "tok_per_s")?.value).toBe(0);
    expect(entries.some((entry) => entry.key === "llm_duration_ms")).toBe(
      false,
    );
  });
});

describe("collapseTurns", () => {
  it("groups consecutive events that share a turn_id", () => {
    const groups = collapseTurns([
      event({ event_id: "1", kind: "user", turn_id: "t1" }),
      event({ event_id: "2", kind: "assistant", turn_id: "t1" }),
      event({ event_id: "3", kind: "user", turn_id: "t2" }),
    ]);
    expect(groups.map((group) => group.map((ev) => ev.event_id))).toEqual([
      ["1", "2"],
      ["3"],
    ]);
  });

  it("falls back to USER boundaries when turn_id is missing", () => {
    const groups = collapseTurns([
      event({ event_id: "s", kind: "system", turn_id: null }),
      event({ event_id: "u1", kind: "user", turn_id: null }),
      event({ event_id: "a1", kind: "assistant", turn_id: null }),
      event({ event_id: "t1", kind: "tool", turn_id: null }),
      event({ event_id: "u2", kind: "user", turn_id: null }),
      event({ event_id: "a2", kind: "assistant", turn_id: null }),
    ]);
    expect(groups.map((group) => group.map((ev) => ev.event_id))).toEqual([
      ["s"],
      ["u1", "a1", "t1"],
      ["u2", "a2"],
    ]);
  });
});

describe("collapseCalls", () => {
  it("folds tool rows under the preceding assistant and drops orphan tools", () => {
    const groups = collapseCalls([
      event({ event_id: "1", kind: "tool" }),
      event({ event_id: "2", kind: "tool" }),
      event({ event_id: "3", kind: "assistant" }),
      event({ event_id: "4", kind: "tool" }),
      event({ event_id: "5", kind: "tool" }),
      event({ event_id: "6", kind: "user" }),
    ]);
    expect(groups.map((group) => group.map((ev) => ev.event_id))).toEqual([
      ["3", "4", "5"],
      ["6"],
    ]);
  });
});

describe("collapseCallRows", () => {
  it("keeps the assistant and inserts a separate DSH summary row", () => {
    const rows = collapseCallRows([
      event({
        event_id: "a",
        kind: "assistant",
        summary: "(tool call only)",
        payload: { tool_call_only: true, content: "" },
      }),
      event({
        event_id: "t1",
        kind: "tool",
        payload: { name: "todo_write" },
      }),
      event({
        event_id: "t2",
        kind: "tool",
        payload: { name: "bash" },
      }),
      event({
        event_id: "t3",
        kind: "tool",
        payload: { name: "bash" },
      }),
      event({
        event_id: "t4",
        kind: "tool",
        payload: { name: "glob" },
      }),
      event({
        event_id: "u",
        kind: "user",
        summary: "next",
      }),
    ]);
    expect(rows.map((row) => row.event_id)).toEqual([
      "a",
      "a__assistant_summary",
      "u",
    ]);
    expect(rows[0]?.payload.tool_call_only).toBe(true);
    expect(rows[0]?.summary).toBe("(tool call only)");
    expect(rows[1]?.payload.collapsed_summary).toBe(true);
    expect(rows[1]?.payload.content).toBe(
      "4 tool calls · todo_write, bash, glob",
    );
  });

  it("formats singular tool call counts", () => {
    expect(formatCollapsedToolCalls(1, ["read"])).toBe("1 tool call · read");
  });
});

describe("ensureToolCallParents", () => {
  it("inserts a tool-call-only assistant before orphan tool bursts", () => {
    const rows = ensureToolCallParents([
      event({ event_id: "u", kind: "user" }),
      event({ event_id: "t1", kind: "tool", summary: "tool ls" }),
      event({ event_id: "t2", kind: "tool", summary: "tool ls" }),
      event({
        event_id: "a",
        kind: "assistant",
        summary: "done",
        payload: { content: "done" },
      }),
    ]);
    expect(rows.map((row) => row.kind)).toEqual([
      "user",
      "assistant",
      "tool",
      "tool",
      "assistant",
    ]);
    expect(rows[1]?.payload.tool_call_only).toBe(true);
    expect(rows[1]?.summary).toBe("(tool call only)");
  });

  it("does not duplicate parents when an assistant already precedes tools", () => {
    const rows = ensureToolCallParents([
      event({
        event_id: "a",
        kind: "assistant",
        summary: "(tool call only)",
        payload: { tool_call_only: true },
      }),
      event({ event_id: "t1", kind: "tool" }),
    ]);
    expect(rows.map((row) => row.event_id)).toEqual(["a", "t1"]);
  });
});

describe("formatDurationMs", () => {
  it("formats compact DSH-style durations", () => {
    expect(formatDurationMs(45)).toBe("45ms");
    expect(formatDurationMs(1200)).toBe("1.2s");
    expect(formatDurationMs(12_500)).toBe("13s");
    expect(formatDurationMs(74_370)).toBe("1m14s");
  });
});

describe("kindLabelFor", () => {
  it("maps kinds to DSH uppercase labels", () => {
    expect(kindLabelFor("assistant")).toBe("ASSISTANT");
    expect(kindLabelFor("tool")).toBe("TOOL");
    expect(kindLabelFor("user")).toBe("USER");
  });
});
