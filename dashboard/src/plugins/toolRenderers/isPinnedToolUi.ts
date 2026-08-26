import type { ChatMessage } from "../../pages/Chat/hooks/useChat";
import type { AssistantTurnSplit } from "../../pages/Chat/utils/messageContent";
import { parseOctopToolOutput } from "./parseToolOutput";
import { resolveToolRenderer } from "./registry";
import { lookupPluginIdForTool } from "./toolPluginIndex";

export function isSilentPluginUiData(data: unknown): boolean {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  const rec = data as Record<string, unknown>;
  if (rec.silent === true) return true;
  if (Array.isArray(rec.items) && rec.items.length === 0) return true;
  return false;
}

/**
 * Tools with custom / structured UI render as sibling blocks outside the
 * foldable process body. They still count toward the summary headline
 * (``已调用 N 次工具``); only their detail UI is pinned out of the fold.
 */
export function isPinnedToolUiMessage(message: ChatMessage): boolean {
  const toolData = message.toolData;
  if (!toolData) return false;
  const parsed = parseOctopToolOutput(toolData.output);
  if (parsed.octopUi) {
    if (isSilentPluginUiData(parsed.data)) return false;
    return true;
  }
  const pluginId =
    toolData.pluginId ?? lookupPluginIdForTool(toolData.name) ?? null;
  const reg = resolveToolRenderer({
    toolName: toolData.name,
    pluginId,
    parsed,
  });
  return reg != null && reg.id !== "default" && reg.pluginId !== "builtin";
}

/** Split rich-UI tools out of the foldable process summary. */
export function partitionPinnedTools(split: AssistantTurnSplit): {
  pinned: ChatMessage[];
  folded: AssistantTurnSplit;
} {
  const pinned: ChatMessage[] = [];
  const pinnedIds = new Set<string>();
  for (const step of split.processSteps) {
    if (step.kind === "tool" && isPinnedToolUiMessage(step.message)) {
      pinned.push(step.message);
      pinnedIds.add(step.message.id);
    }
  }
  if (pinned.length === 0) {
    return { pinned, folded: split };
  }
  return {
    pinned,
    folded: {
      tools: split.tools.filter((m) => !pinnedIds.has(m.id)),
      thinkings: split.thinkings,
      processSteps: split.processSteps.filter(
        (s) => s.kind === "thinking" || !pinnedIds.has(s.message.id),
      ),
      answerMessage: split.answerMessage,
    },
  };
}
