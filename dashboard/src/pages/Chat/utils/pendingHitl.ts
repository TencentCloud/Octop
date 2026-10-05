import {
  ASK_USER_TOOL_NAME,
  extractAskQuestions,
  isAskHitl,
  questionsFromUnknown,
  type AskQuestion,
} from "../../../api/types/hitl";
import type { ChatMessage, HitlActionRequest } from "../hooks/sseHelpers";
import type { HitlSessionPolicy } from "./hitlSessionPolicy";

export type PendingAsk = {
  messageId: string;
  actions: HitlActionRequest[];
  questions: AskQuestion[];
};

/** True when a pending HITL can actually be resumed on the server. */
export function isResumableHitl(
  hitl: ChatMessage["hitlData"] | undefined,
): boolean {
  return Boolean(hitl?.pending_id?.trim());
}

/** Unanswered ``ask_user_question`` is a pause, not a running tool. */
export function isPausedAskTool(message: ChatMessage): boolean {
  return (
    message.toolData?.name === ASK_USER_TOOL_NAME &&
    message.toolData.output === undefined
  );
}

/** True when any message still awaits a recoverable HITL decision. */
export function hasPendingHitl(messages: ChatMessage[]): boolean {
  return messages.some((message) => {
    const hitl = message.hitlData;
    if (!hitl || (hitl.status ?? "pending") !== "pending") return false;
    if (isAskHitl(hitl.action_requests) && !isResumableHitl(hitl)) return false;
    return true;
  });
}

export type PendingApproval = {
  messageId: string;
  actions: HitlActionRequest[];
};

/** Latest pending tool-approval card, if any (questions are excluded). */
export function findPendingApproval(
  messages: ChatMessage[],
): PendingApproval | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    const hitl = message.hitlData;
    if (
      !hitl ||
      (hitl.status ?? "pending") !== "pending" ||
      isAskHitl(hitl.action_requests) ||
      !hitl.action_requests?.length
    ) {
      continue;
    }
    return {
      messageId: message.id,
      actions: hitl.action_requests,
    };
  }
  return null;
}

/** Pending tool approval that a session bypass can resume without asking. */
export function findAutoResumableApproval(
  policy: HitlSessionPolicy,
  messages: ChatMessage[],
): PendingApproval | null {
  const pending = findPendingApproval(messages);
  if (!pending) return null;
  if (policy.mode === "allow_all") return pending;
  if (policy.mode === "allow_tools") {
    const allowed = new Set(policy.tools ?? []);
    if (
      pending.actions.length > 0 &&
      pending.actions.every((action) => allowed.has(action.name))
    ) {
      return pending;
    }
  }
  return null;
}

function askActionsFromTool(message: ChatMessage): HitlActionRequest[] | null {
  if (message.toolData?.name !== ASK_USER_TOOL_NAME) return null;
  if (message.toolData.output !== undefined) return null;
  const questions = questionsFromUnknown(message.toolData.arguments);
  if (questions.length === 0) return null;
  return [{ name: ASK_USER_TOOL_NAME, args: { questions } }];
}

/** Turn an unanswered ``ask_user_question`` tool bubble into a pending HITL card. */
export function promoteAskUserToolMessage(message: ChatMessage): ChatMessage {
  if (message.hitlData) return message;
  const actions = askActionsFromTool(message);
  if (!actions) return message;
  return {
    ...message,
    hitlData: {
      action_requests: actions,
      status: "pending",
    },
    status: "done",
  };
}

/** Latest pending ``ask_user_question`` card, if any. */
export function findPendingAsk(messages: ChatMessage[]): PendingAsk | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    const hitl = message.hitlData;
    if (
      !hitl ||
      (hitl.status ?? "pending") !== "pending" ||
      !isAskHitl(hitl.action_requests) ||
      !isResumableHitl(hitl)
    ) {
      continue;
    }
    const questions = extractAskQuestions(hitl.action_requests);
    if (questions.length > 0) {
      return {
        messageId: message.id,
        actions: hitl.action_requests,
        questions,
      };
    }
  }
  return null;
}
