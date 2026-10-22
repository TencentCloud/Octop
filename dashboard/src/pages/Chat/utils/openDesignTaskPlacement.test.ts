import { describe, expect, it } from "vitest";
import type { DesignTask } from "../../../api/modules/openDesign";
import type { ChatMessage } from "../hooks/useChat";
import { groupConsecutiveAssistantMessages } from "./messageGrouping";
import { placeOpenDesignTasks } from "./openDesignTaskPlacement";

const task = (id: string, status = "succeeded"): DesignTask => ({
  task_id: id,
  instance_id: "i",
  project: "p",
  run_id: id,
  status,
  last_error: null,
  result: {},
  revision: 1,
  created_at: 1,
  updated_at: 1,
});
const message = (
  id: string,
  role: ChatMessage["role"],
  extra: Partial<ChatMessage> = {},
): ChatMessage => ({ id, role, content: "", timestamp: 1, ...extra });
const start = (id: string, run: string) =>
  message(id, "assistant", {
    toolData: {
      name: "open-design__i_start_run",
      output: JSON.stringify([
        { type: "text", text: JSON.stringify({ runId: run }) },
      ]),
    },
  });

describe("OpenDesign task placement", () => {
  it("keeps completed and new running tasks at their own turn endings", () => {
    const groups = groupConsecutiveAssistantMessages([
      message("u1", "user"),
      start("s1", "r1"),
      message("a1", "assistant"),
      message("u2", "user"),
      start("s2", "r2"),
      message("a2", "assistant"),
    ]);
    const placement = placeOpenDesignTasks(groups, [
      task("r2", "running"),
      task("r1"),
    ]);
    expect(placement.byGroup.get("s1")?.map((t) => t.task_id)).toEqual(["r1"]);
    expect(placement.byGroup.get("s2")?.map((t) => t.task_id)).toEqual(["r2"]);
    expect(placement.pending).toEqual([]);
    expect([
      ...placeOpenDesignTasks(groups, [task("r2"), task("r1")]).byGroup.keys(),
    ]).toEqual([...placement.byGroup.keys()]);
  });
  it("never moves a task to a later status query or idempotent resubmission", () => {
    const groups = groupConsecutiveAssistantMessages([
      message("u1", "user"),
      start("original", "r1"),
      message("u2", "user"),
      message("query", "assistant", {
        toolData: { name: "open-design__i_get_run", output: '{"runId":"r1"}' },
      }),
      message("u3", "user"),
      start("retry", "r1"),
    ]);
    expect([
      ...placeOpenDesignTasks(groups, [task("r1")]).byGroup.keys(),
    ]).toEqual(["original"]);
  });
  it("waits for older history instead of showing completed tasks in the new turn", () => {
    const recent = groupConsecutiveAssistantMessages([
      message("u2", "user"),
      start("s2", "r2"),
    ]);
    const tasks = [task("r2", "running"), task("r1")];
    expect([...placeOpenDesignTasks(recent, tasks).byGroup.keys()]).toEqual([
      "s2",
    ]);
    expect(placeOpenDesignTasks(recent, tasks).pending).toEqual([]);
    const loaded = groupConsecutiveAssistantMessages([
      message("u1", "user"),
      start("s1", "r1"),
      ...recent.flatMap((g) => g.messages),
    ]);
    expect(
      placeOpenDesignTasks(loaded, tasks).byGroup.get("s1")?.[0].task_id,
    ).toBe("r1");
  });
  it("accepts structured artifacts and split call/result messages", () => {
    const groups = groupConsecutiveAssistantMessages([
      message("call", "assistant", {
        toolData: { name: "open-design__i_start_run", callId: "c" },
      }),
      message("result", "tool", {
        toolData: {
          callId: "c",
          artifact: { structured_content: { runId: "r" } },
        },
      }),
    ]);
    expect(
      placeOpenDesignTasks(groups, [task("r")]).byGroup.get("call")?.[0]
        .task_id,
    ).toBe("r");
  });
  it("anchors paginated history with server-provided original-turn message IDs", () => {
    const groups = groupConsecutiveAssistantMessages([
      message("final1", "assistant"),
      message("u2", "user"),
      message("final2", "assistant"),
    ]);
    const tasks = [
      { ...task("r1"), anchor_message_ids: ["final1", "unloaded-start1"] },
      { ...task("r2"), anchor_message_ids: ["final2", "unloaded-start2"] },
    ];
    const placed = placeOpenDesignTasks(groups, tasks);
    expect(placed.byGroup.get("final1")?.[0].task_id).toBe("r1");
    expect(placed.byGroup.get("final2")?.[0].task_id).toBe("r2");
    expect(placed.pending).toEqual([]);
  });
  it("keeps unacknowledged active submissions pending without inventing a history anchor", () => {
    expect(
      placeOpenDesignTasks(
        [],
        [task("unknown", "queued"), task("finished")],
      ).pending.map((t) => t.task_id),
    ).toEqual(["unknown"]);
  });
});
