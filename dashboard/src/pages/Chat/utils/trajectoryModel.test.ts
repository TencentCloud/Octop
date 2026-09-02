import { describe, expect, it } from "vitest";
import type {
  TrajectoryEvent,
  TrajectoryMetrics,
} from "../../../api/modules/trajectory";
import {
  collapseCalls,
  collapseTurns,
  filterRows,
  laneForKind,
  toLedgerRow,
  visibleMetrics,
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

  it("omits requestSeq when the event has none", () => {
    const row = toLedgerRow(event({ event_id: "u1", kind: "user" }));
    expect(row.requestSeq).toBeUndefined();
  });
});

describe("filterRows", () => {
  const rows = [
    {
      id: "1",
      kind: "tool",
      title: "read_file",
      summary: "open a.py",
      isError: false,
    },
    {
      id: "2",
      kind: "assistant",
      title: "Request #1",
      summary: "I'll look at the source",
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

  it("does not merge events that lack a turn_id", () => {
    const groups = collapseTurns([
      event({ event_id: "1", kind: "system", turn_id: null }),
      event({ event_id: "2", kind: "system", turn_id: null }),
    ]);
    expect(groups).toHaveLength(2);
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
