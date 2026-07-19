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

export function splitAssistantTurn(
  messages: ChatMessage[],
): AssistantTurnSplit {
  let answerIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    const { textContent } = deriveMessageContent(messages[i]);
    if (textContent.trim()) {
      answerIdx = i;
      break;
    }
  }

  const tools: ChatMessage[] = [];
  const thinkings: ThinkingProcessItem[] = [];
  const processSteps: ProcessStep[] = [];

  const pushMessageSteps = (msg: ChatMessage, thinkingStreaming = false) => {
    const { thinkingParts } = deriveMessageContent(msg);
    const thinkingContent = thinkingParts.join("").trim();
    if (thinkingContent) {
      const item: ThinkingProcessItem = {
        messageId: msg.id,
        content: thinkingContent,
        isStreaming: thinkingStreaming,
      };
      thinkings.push(item);
      processSteps.push({ kind: "thinking", item });
    }
    if (msg.toolData) {
      tools.push(msg);
      processSteps.push({ kind: "tool", message: msg });
    }
  };

  if (answerIdx === -1) {
    for (const msg of messages) {
      pushMessageSteps(msg, msg.status === "streaming");
    }
    return { tools, thinkings, processSteps, answerMessage: null };
  }

  for (let i = 0; i < answerIdx; i++) {
    pushMessageSteps(messages[i]);
  }

  const answerMessage = messages[answerIdx];
  pushMessageSteps(
    answerMessage,
    answerMessage.status === "streaming" &&
      !deriveMessageContent(answerMessage).textContent.trim(),
  );

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
