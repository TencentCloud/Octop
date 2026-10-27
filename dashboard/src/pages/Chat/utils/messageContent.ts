import type { ChatMessage, DecisionNotice } from "../hooks/useChat";
import { isBrowserToolName, isWriteToolName } from "../constants";

const THINKING_TAG_RE = /<(?:think|thinking)>[\s\S]*?<\/(?:think|thinking)>/gi;
const THINKING_OPEN_RE = /<(?:think|thinking)>/i;
const THINKING_CLOSE_RE = /<\/(?:think|thinking)>/i;

/** Strip `<think>` / `<thinking>` blocks from visible assistant text. */
export function stripThinkTags(raw: string): string {
  let result = raw.replace(THINKING_TAG_RE, "");
  // Orphan closing tag: drop the hidden prefix before it.
  while (true) {
    const close = result.search(THINKING_CLOSE_RE);
    if (close < 0) break;
    const open = result.search(THINKING_OPEN_RE);
    if (open >= 0 && open < close) break;
    result = result.slice(close).replace(THINKING_CLOSE_RE, "");
  }
  const unclosed = result.search(THINKING_OPEN_RE);
  if (unclosed >= 0) {
    result = result.slice(0, unclosed);
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
  | { kind: "tool"; message: ChatMessage }
  | { kind: "decision"; notice: DecisionNotice };

export interface AssistantTurnSplit {
  tools: ChatMessage[];
  thinkings: ThinkingProcessItem[];
  processSteps: ProcessStep[];
  answerMessage: ChatMessage | null;
  /** Stream failures stay out of the answer so the error box is only the error. */
  errorMessages?: ChatMessage[];
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

/**
 * Tools that hand the turn over to another speaker (``ask_agent``). Only these
 * can legitimately produce a "narration → delegation → fresh conclusion" turn
 * where the pre-tool text is superseded by the conclusion.
 *
 * Ordinary tools (read / edit / shell / …) continue the *same* answer, so the
 * text on both sides of them must stay joined — otherwise a settled turn
 * silently drops the main answer and shows only the closing sentence.
 */
const DELEGATION_TOOL_NAMES = ["ask_agent"] as const;

function isDelegationToolName(name: string | undefined): boolean {
  const trimmed = (name ?? "").trim();
  const slash = trimmed.lastIndexOf("/");
  const base = (slash >= 0 ? trimmed.slice(slash + 1) : trimmed).toLowerCase();
  return (DELEGATION_TOOL_NAMES as readonly string[]).includes(base);
}

/** True when a completed delegation sits between two visible text bubbles (1:1 ReAct). */
function hasCompletedDelegationBetweenTexts(messages: ChatMessage[]): boolean {
  let sawText = false;
  let sawDelegationAfterText = false;
  for (const msg of messages) {
    const { textContent } = deriveMessageContent(msg);
    if (
      msg.toolData?.output &&
      sawText &&
      isDelegationToolName(msg.toolData.name)
    ) {
      sawDelegationAfterText = true;
    }
    if (!msg.toolData && textContent.trim() && sawDelegationAfterText) {
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
  opts?: { joinAnswerFragments?: boolean },
): AssistantTurnSplit {
  const tools: ChatMessage[] = [];
  const thinkings: ThinkingProcessItem[] = [];
  const processSteps: ProcessStep[] = [];
  const textParts: string[] = [];
  const errorMessages: ChatMessage[] = [];
  const decision = messages.find((item) => item.decision)?.decision;
  if (decision) {
    processSteps.push({ kind: "decision", notice: decision });
  }
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
    if (msg.status === "error") {
      const errorText =
        textContent.trim() || msg.errorInfo?.message?.trim() || "";
      errorMessages.push({
        ...msg,
        content: errorText,
        contentBlocks: undefined,
      });
      continue;
    }
    if (textContent.trim()) {
      textParts.push(textContent);
      answerTemplate = msg;
      answerStreaming = msg.status === "streaming";
    }
  }

  // 1:1 ReAct narration + tools is one answer: join every text fragment so the
  // main answer never collapses to just the closing sentence once the turn
  // settles. Only a *delegation* hand-off (text → ask_agent → fresh answer)
  // supersedes the pre-tool narration and keeps the last bubble.
  const teamStamped = messages.some((item) =>
    Boolean((item.speakerAgentId || "").trim()),
  );
  const joinFragments =
    textParts.length > 1 &&
    (Boolean(opts?.joinAnswerFragments) ||
      teamStamped ||
      messages.some((item) => item.teamWrapup) ||
      !hasCompletedDelegationBetweenTexts(messages));
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

  return { tools, thinkings, processSteps, answerMessage, errorMessages };
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
  if ((split?.tools ?? []).some((msg) => messageUsesFileTool(msg))) {
    return true;
  }
  return (split?.answerMessage?.editedFiles?.length ?? 0) > 0;
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
