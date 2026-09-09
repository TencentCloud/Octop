import type { TodoListItem } from "../../../utils/parseWriteTodos";
import {
  collectWriteTodosFromMessages,
  type WriteTodosMessageSource,
} from "../../../utils/parseWriteTodos";
import type { ChatMessage } from "../hooks/useChat";
import { deriveMessageContent } from "./messageContent";

/** Lines that tell the user how to operate Plan/Craft UI — never show in chat. */
const MODE_UI_INSTRUCTION_RE =
  /手动切换|模式选择按钮|输入框旁边|切换入口|切换到\s*默认|切换到\s*做一做|切回默认|请.*切换.*模式|switch to (?:default|craft)|mode (?:selection )?button|chat input|做一做[）)]?\s*模式|Craft\s*[/／]\s*做一做|修改类工具不可用|仍在计划模式/i;

/**
 * Remove assistant copy that instructs the user to flip the composer mode
 * control. Product UI (PlanReadyCard) owns that handoff.
 */
export function stripConversationModeUiInstructions(text: string): string {
  const raw = text.replace(/\r\n/g, "\n").trim();
  if (!raw) return "";

  const blocks = raw.split(/\n{2,}/);
  const kept = blocks.filter((block) => {
    const compact = block.replace(/\s+/g, "");
    if (!compact) return false;
    if (MODE_UI_INSTRUCTION_RE.test(block)) return false;
    // Whole block is only a mode-name reminder.
    if (
      /^(当前)?(仍?在)?计划|仅问答|Ask|Plan|Craft/.test(compact) &&
      compact.length < 40
    ) {
      return !/模式|mode|不可用|unavailable/i.test(block);
    }
    return true;
  });

  // Also drop leftover single lines that match.
  const lines = kept.join("\n\n").split("\n");
  const cleaned = lines
    .filter((line) => !MODE_UI_INSTRUCTION_RE.test(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return cleaned;
}

/** Build the Craft-turn user message that carries an approved plan brief. */
export function buildPlanExecuteMessage(brief: string): string {
  const cleaned = brief.trim();
  if (!cleaned) {
    return "Execute the plan we just prepared.";
  }
  return cleaned.endsWith("\n") ? cleaned : `${cleaned}\n`;
}

export function formatPlanBrief(params: {
  summary?: string;
  todos?: TodoListItem[];
}): string {
  const lines: string[] = ["## Approved plan", ""];
  const summary = stripConversationModeUiInstructions(
    params.summary || "",
  ).trim();
  if (summary) {
    lines.push(summary, "");
  }
  const todos = params.todos || [];
  if (todos.length > 0) {
    lines.push("### Steps");
    todos.forEach((todo, index) => {
      const status = todo.status ? ` (${todo.status})` : "";
      lines.push(`${index + 1}. ${todo.content}${status}`);
    });
    lines.push("");
  }
  lines.push("Execute this plan now.");
  return `${lines.join("\n").trim()}\n`;
}

/** Collect plan brief from the latest assistant turn (text + write_todos). */
export function buildPlanBriefFromMessages(
  messages: readonly ChatMessage[],
): string | null {
  const sources = messages as unknown as WriteTodosMessageSource[];
  const todos = collectWriteTodosFromMessages(sources);
  let summary = "";
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (!msg || msg.role !== "assistant" || msg.toolData) continue;
    summary = stripConversationModeUiInstructions(
      deriveMessageContent(msg).textContent,
    ).trim();
    if (summary) break;
  }
  if (!summary && todos.length === 0) return null;
  return formatPlanBrief({ summary, todos });
}

/** Minimal user-turn text for silent Plan→Craft (matched on history reload). */
export const PLAN_EXECUTE_USER_TRIGGER = "Execute the approved plan now.";

/** P7: Execute plan → Craft mode; brief goes via metadata (not chat text). */
export function planExecuteHandoff(brief: string): {
  conversationMode: "craft";
  /** Silent send — no visible user bubble; planBrief drives the turn. */
  hideUserMessage: true;
  /** Non-empty WS text so servers that only check text still accept the turn. */
  text: string;
  planBrief: string;
} {
  return {
    conversationMode: "craft",
    hideUserMessage: true,
    text: PLAN_EXECUTE_USER_TRIGGER,
    planBrief: brief.trim(),
  };
}

/** P8: Keep planning → stay in Plan mode. */
export function planContinueHandoff(): { conversationMode: "plan" } {
  return { conversationMode: "plan" };
}
