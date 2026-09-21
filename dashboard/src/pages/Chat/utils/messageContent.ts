import type { ChatMessage } from "../hooks/useChat";
import { isBrowserToolName, isWriteToolName } from "../constants";

const THINKING_TAG_RE = /<think>[\s\S]*?<\/think>/g;

/** Strip `<think>` blocks from visible assistant text. */
export function stripThinkTags(raw: string): string {
  let result = raw.replace(THINKING_TAG_RE, "");
  const unclosedIdx = result.indexOf("<think>");
  if (unclosedIdx >= 0) {
    result = result.slice(0, unclosedIdx);
  }
  return result.trim();
}

export function deriveMessageContent(message: ChatMessage): {
  thinkingParts: string[];
  textContent: string;
} {
  if (message.contentBlocks && message.contentBlocks.length > 0) {
    const thinkingParts: string[] = [];
    let text = "";
    for (const block of message.contentBlocks) {
      if (block.type === "thinking" && block.content.trim()) {
        thinkingParts.push(block.content);
      } else if (block.type === "text") {
        text += block.content;
      }
    }
    if (text) {
      text = stripThinkTags(text);
    } else if (message.content) {
      text = stripThinkTags(message.content);
    }
    return { thinkingParts, textContent: text };
  }

  if (message.type === "reasoning" && message.content) {
    return { thinkingParts: [message.content], textContent: "" };
  }

  return {
    thinkingParts: [],
    textContent: message.content ? stripThinkTags(message.content) : "",
  };
}

export interface ThinkingProcessItem {
  messageId: string;
  content: string;
  isStreaming?: boolean;
}

export type ProcessStep =
  | { kind: "thinking"; item: ThinkingProcessItem }
  | { kind: "tool"; message: ChatMessage };

export interface AssistantTurnSplit {
  tools: ChatMessage[];
  thinkings: ThinkingProcessItem[];
  processSteps: ProcessStep[];
  answerMessage: ChatMessage | null;
}

function joinAnswerParts(parts: string[]): string {
  let out = "";
  for (const part of parts) {
    if (!part) continue;
    if (!out) {
      out = part;
      continue;
    }
    if (part === out || out.endsWith(part)) continue;
    if (part.startsWith(out) || part.endsWith(out)) {
      out = part.length > out.length ? part : out;
      continue;
    }
    const needSpace =
      !/\s$/u.test(out) &&
      !/^\s/u.test(part) &&
      !/^[，。！？、,.!?;:]/u.test(part);
    out += needSpace ? ` ${part}` : part;
  }
  return out;
}

/** True when a completed tool sits between two visible text bubbles (1:1 ReAct). */
function hasCompletedToolBetweenTexts(messages: ChatMessage[]): boolean {
  let sawText = false;
  let sawToolAfterText = false;
  for (const msg of messages) {
    const { textContent } = deriveMessageContent(msg);
    if (msg.toolData?.output && sawText) {
      sawToolAfterText = true;
    }
    if (!msg.toolData && textContent.trim() && sawToolAfterText) {
      return true;
    }
    if (!msg.toolData && textContent.trim()) {
      sawText = true;
    }
  }
  return false;
}

export function splitAssistantTurn(
  messages: ChatMessage[],
): AssistantTurnSplit {
  const tools: ChatMessage[] = [];
  const thinkings: ThinkingProcessItem[] = [];
  const processSteps: ProcessStep[] = [];
  const textParts: string[] = [];
  let answerTemplate: ChatMessage | null = null;
  let answerStreaming = false;

  for (const msg of messages) {
    const { thinkingParts, textContent } = deriveMessageContent(msg);
    const thinkingContent = thinkingParts.join("").trim();
    if (thinkingContent) {
      const item: ThinkingProcessItem = {
        messageId: msg.id,
        content: thinkingContent,
        isStreaming: msg.status === "streaming" && !textContent.trim(),
      };
      thinkings.push(item);
      processSteps.push({ kind: "thinking", item });
    }
    if (msg.toolData) {
      tools.push(msg);
      processSteps.push({ kind: "tool", message: msg });
      continue;
    }
    if (textContent.trim()) {
      textParts.push(textContent);
      answerTemplate = msg;
      answerStreaming = msg.status === "streaming";
    }
  }

  // 1:1 ReAct (text → tool → conclusion) keeps the last bubble as the answer.
  // Join only team fragments of the same speaker that were split across bubbles.
  const joinFragments =
    textParts.length > 1 &&
    (messages.some((item) => item.teamWrapup) ||
      !hasCompletedToolBetweenTexts(messages));
  const answerMessage =
    answerTemplate && textParts.length > 0
      ? {
          ...answerTemplate,
          content: joinFragments
            ? joinAnswerParts(textParts)
            : textParts[textParts.length - 1],
          contentBlocks: undefined,
          status: answerStreaming
            ? ("streaming" as const)
            : answerTemplate.status,
        }
      : null;

  return { tools, thinkings, processSteps, answerMessage };
}

export function toAnswerOnlyMessage(message: ChatMessage): ChatMessage {
  const { textContent } = deriveMessageContent(message);
  const textBlocks =
    message.contentBlocks?.filter((block) => block.type === "text") ?? [];
  return {
    ...message,
    content: textContent,
    contentBlocks: textBlocks.length > 0 ? textBlocks : undefined,
    toolData: undefined,
  };
}

export function countProcessStats(split: AssistantTurnSplit): {
  toolCount: number;
  thinkingCount: number;
} {
  const tools = split?.tools ?? [];
  const thinkings = split?.thinkings ?? [];
  return {
    toolCount: tools.length,
    thinkingCount: thinkings.length,
  };
}

export function turnUsedBrowserTool(split: AssistantTurnSplit): boolean {
  return (split?.tools ?? []).some((msg) =>
    isBrowserToolName(msg.toolData?.name),
  );
}

/** True when this message is a workspace file write/edit tool call. */
function messageUsesFileTool(msg: ChatMessage): boolean {
  return isWriteToolName(msg.toolData?.name);
}

/** True when this assistant turn invoked a workspace file write/edit tool. */
export function turnUsedFileTool(split: AssistantTurnSplit): boolean {
  return (split?.tools ?? []).some((msg) => messageUsesFileTool(msg));
}

/** Index of the most recent assistant turn that invoked a browser tool, or -1. */
export function findLastBrowserTurnGroupIndex(
  groups: ReadonlyArray<{ messages: ReadonlyArray<ChatMessage> }>,
): number {
  for (let i = groups.length - 1; i >= 0; i--) {
    const group = groups[i];
    if (!group.messages.some((m) => m.role === "assistant")) continue;
    if (turnUsedBrowserTool(splitAssistantTurn([...group.messages]))) return i;
  }
  return -1;
}
