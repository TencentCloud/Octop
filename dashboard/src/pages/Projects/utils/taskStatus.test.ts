import { describe, expect, it } from "vitest";
import {
  asTaskStatus,
  COLUMN_STATUSES,
  isTransitionAllowed,
  STATUS_COLORS,
  STATUS_LABEL_KEYS,
  STATUS_TRANSITIONS,
  TERMINAL_STATUSES,
} from "./taskStatus";

/** 词表权威 = PLAN.md §1.1（7 态，planning 最前）。 */
const ALL_STATUSES = [
  "planning",
  "todo",
  "doing",
  "review",
  "blocked",
  "done",
  "cancelled",
] as const;

describe("taskStatus 单一来源", () => {
  it("7 态齐全：三张映射的键集与词表逐字一致", () => {
    expect([...COLUMN_STATUSES].sort()).toEqual([...ALL_STATUSES].sort());
    expect(Object.keys(STATUS_LABEL_KEYS).sort()).toEqual(
      [...ALL_STATUSES].sort(),
    );
    expect(Object.keys(STATUS_COLORS).sort()).toEqual([...ALL_STATUSES].sort());
    expect(Object.keys(STATUS_TRANSITIONS).sort()).toEqual(
      [...ALL_STATUSES].sort(),
    );
  });

  it("★ 键顺序也必须与 COLUMN_STATUSES 同序（不只是集合相等）", () => {
    expect(Object.keys(STATUS_LABEL_KEYS)).toEqual(COLUMN_STATUSES);
    expect(Object.keys(STATUS_COLORS)).toEqual(COLUMN_STATUSES);
    expect(Object.keys(STATUS_TRANSITIONS)).toEqual(COLUMN_STATUSES);
  });

  it("COLUMN_STATUSES 与 PLAN §4.1/§1.1 同构：planning 最前，既有 6 值相对序不变", () => {
    expect(COLUMN_STATUSES).toEqual([
      "planning",
      "todo",
      "doing",
      "review",
      "blocked",
      "done",
      "cancelled",
    ]);
  });

  it("TERMINAL_STATUSES 仍为 [done, cancelled]，planning 不属于终态（S-1）", () => {
    expect(TERMINAL_STATUSES).toEqual(["done", "cancelled"]);
    expect(TERMINAL_STATUSES).not.toContain("planning");
    for (const status of TERMINAL_STATUSES) {
      expect(COLUMN_STATUSES).toContain(status);
    }
  });

  it("STATUS_TRANSITIONS 邻接逐字照 PLAN §1.2（含 planning 双向与 cancelled 空集）", () => {
    expect(STATUS_TRANSITIONS).toEqual({
      planning: ["todo", "cancelled"],
      todo: ["planning", "doing", "blocked", "cancelled"],
      doing: ["todo", "review", "done", "blocked", "cancelled"],
      review: ["doing", "done", "blocked", "cancelled"],
      blocked: ["todo", "doing", "cancelled"],
      done: ["doing"],
      cancelled: [],
    });
    // 每个出边都必须是已知状态。
    for (const targets of Object.values(STATUS_TRANSITIONS)) {
      for (const target of targets) {
        expect(COLUMN_STATUSES).toContain(target);
      }
    }
  });

  it("planning 的入边恰为 {创建默认, todo→planning}", () => {
    const entries = ALL_STATUSES.filter((from) =>
      STATUS_TRANSITIONS[from].includes("planning"),
    );
    expect(entries).toEqual(["todo"]);
    expect(isTransitionAllowed("todo", "planning")).toBe(true);
    expect(isTransitionAllowed("planning", "todo")).toBe(true);
    expect(isTransitionAllowed("planning", "done")).toBe(false);
    expect(isTransitionAllowed("cancelled", "todo")).toBe(false);
  });

  it("asTaskStatus：合法值原样返回，未知/非字符串返回 null", () => {
    for (const status of ALL_STATUSES) {
      expect(asTaskStatus(status)).toBe(status);
    }
    expect(asTaskStatus("nope")).toBeNull();
    expect(asTaskStatus(null)).toBeNull();
    expect(asTaskStatus(undefined)).toBeNull();
    expect(asTaskStatus(3)).toBeNull();
    expect(asTaskStatus({ status: "todo" })).toBeNull();
  });

  it("label 键名指向 projects 命名空间且 7 态互不相同", () => {
    const keys = Object.values(STATUS_LABEL_KEYS);
    expect(new Set(keys).size).toBe(keys.length);
    for (const key of keys) {
      expect(key.startsWith("projects.taskStatus")).toBe(true);
    }
    expect(STATUS_LABEL_KEYS.planning).toBe("projects.taskStatusPlanning");
  });
});
