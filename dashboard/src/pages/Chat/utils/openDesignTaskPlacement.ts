import type { DesignTask } from "../../../api/modules/openDesign";
import type { MessageGroup } from "./messageGrouping";

function runId(value: unknown, depth = 0): string | undefined {
  if (depth > 5 || value == null) return;
  if (typeof value === "string") {
    try {
      return runId(JSON.parse(value), depth + 1);
    } catch {
      return;
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const id = runId(item, depth + 1);
      if (id) return id;
    }
    return;
  }
  if (typeof value !== "object") return;
  const record = value as Record<string, unknown>;
  if (typeof record.runId === "string") return record.runId;
  for (const key of [
    "structuredContent",
    "structured_content",
    "content",
    "text",
    "output",
  ]) {
    const id = runId(record[key], depth + 1);
    if (id) return id;
  }
}

/** Bind to the first submission, never a later status query or retry. */
export function placeOpenDesignTasks(
  groups: MessageGroup[],
  tasks: DesignTask[],
) {
  const anchors = new Map<string, string>();
  for (const group of groups) {
    const key = group.messages[0]?.id;
    if (!key) continue;
    const calls = new Set(
      group.messages
        .filter(
          (m) =>
            m.toolData?.name?.endsWith("_start_run") ||
            m.toolData?.name === "start_run",
        )
        .map((m) => m.toolData?.callId)
        .filter(Boolean),
    );
    for (const message of group.messages) {
      const tool = message.toolData;
      if (
        !tool ||
        !(
          tool.name?.endsWith("_start_run") ||
          tool.name === "start_run" ||
          (tool.callId && calls.has(tool.callId))
        )
      )
        continue;
      const id = runId(tool.artifact) ?? runId(tool.output);
      if (id && !anchors.has(id)) anchors.set(id, key);
    }
  }
  const byGroup = new Map<string, DesignTask[]>();
  const pending: DesignTask[] = [];
  const groupByMessage = new Map(
    groups.flatMap((group) =>
      group.messages.map(
        (message) => [message.id, group.messages[0].id] as const,
      ),
    ),
  );
  for (const task of [...tasks].reverse()) {
    const original = task.anchor_message_ids?.find((id) =>
      groupByMessage.has(id),
    );
    const key = original
      ? groupByMessage.get(original)
      : task.run_id
      ? anchors.get(task.run_id)
      : undefined;
    if (key) byGroup.set(key, [...(byGroup.get(key) ?? []), task]);
    else if (
      ["submitting", "queued", "running", "unavailable"].includes(task.status)
    )
      pending.push(task);
  }
  return { byGroup, pending };
}
