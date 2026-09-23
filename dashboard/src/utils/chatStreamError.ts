/** Classify and localize chat / model stream failures for user-facing UI. */

import type { TFunction } from "i18next";

const _STREAM_ERROR_KEYS = [
  "stream_errors.stream_stall",
  "stream_errors.rate_limit",
  "stream_errors.auth",
  "stream_errors.insufficient_balance",
  "stream_errors.context_length",
  "stream_errors.recursion_limit",
  "stream_errors.timeout_network",
  "stream_errors.provider_unavailable",
  "stream_errors.model_call_failed",
] as const;

export type StreamErrorKey = (typeof _STREAM_ERROR_KEYS)[number];

export type StreamErrorAction = {
  path: string;
  labelKey: string;
};

const STREAM_ERROR_ACTIONS: Partial<Record<StreamErrorKey, StreamErrorAction>> =
  {
    "stream_errors.auth": {
      path: "/admin/models",
      labelKey: "modelConfig.configureButton",
    },
    "stream_errors.insufficient_balance": {
      path: "/admin/models",
      labelKey: "modelConfig.configureButton",
    },
    "stream_errors.recursion_limit": {
      path: "/agent-config",
      labelKey: "chat.goToAgentConfig",
    },
  };

function normalizeMessage(message: string): string {
  let msg = message.trim();
  const lower = msg.toLowerCase();
  for (const prefix of ["agent error:", "error:"]) {
    if (lower.startsWith(prefix)) {
      msg = msg.slice(prefix.length).trim();
      break;
    }
  }
  return msg;
}

/** Return a stable i18n key for known model/stream failures, else null. */
export function classifyChatStreamError(
  message: string | null | undefined,
): StreamErrorKey | null {
  if (!message) return null;
  const msg = normalizeMessage(message);
  if (!msg) return null;
  const lower = msg.toLowerCase();
  const compact = lower.replace(/[_\s]/g, "");

  if (
    compact.includes("streamchunktimeouterror") ||
    lower.includes("no streaming chunk received") ||
    lower.includes("stream_chunk_timeout")
  ) {
    return "stream_errors.stream_stall";
  }

  if (
    lower.includes("error code: 429") ||
    lower.includes("http 429") ||
    lower.includes("rate_limit") ||
    compact.includes("ratelimiterror") ||
    lower.includes("too many requests")
  ) {
    return "stream_errors.rate_limit";
  }

  if (
    lower.includes("error code: 402") ||
    lower.includes("http 402") ||
    lower.includes("insufficient balance") ||
    lower.includes("insufficient_quota") ||
    lower.includes("insufficient credits") ||
    lower.includes("exceeded your current quota") ||
    lower.includes("payment_required") ||
    lower.includes("billing_not_active") ||
    lower.includes("arrearage") ||
    msg.includes("余额不足") ||
    msg.includes("账户余额") ||
    msg.includes("欠费")
  ) {
    return "stream_errors.insufficient_balance";
  }

  if (
    lower.includes("error code: 401") ||
    lower.includes("http 401") ||
    lower.includes("invalid_api_key") ||
    lower.includes("incorrect api key") ||
    compact.includes("authenticationerror") ||
    (lower.includes("unauthorized") &&
      (lower.includes("api") || lower.includes("key")))
  ) {
    return "stream_errors.auth";
  }

  if (
    lower.includes("context_length_exceeded") ||
    lower.includes("maximum context length") ||
    lower.includes("prompt is too long") ||
    lower.includes("input tokens exceed") ||
    compact.includes("openaicontextoverflowerror")
  ) {
    return "stream_errors.context_length";
  }

  if (
    lower.includes("graph_recursion_limit") ||
    compact.includes("graphrecursionerror") ||
    lower.includes("recursion limit of") ||
    (lower.includes("recursion_limit") &&
      (lower.includes("reached") || lower.includes("without hitting a stop")))
  ) {
    return "stream_errors.recursion_limit";
  }

  if (
    compact.includes("internalservererror") ||
    lower.includes("bad gateway") ||
    lower.includes("service unavailable") ||
    lower.includes("error code: 500") ||
    lower.includes("error code: 502") ||
    lower.includes("error code: 503") ||
    lower.includes("http 500") ||
    lower.includes("http 502") ||
    lower.includes("http 503")
  ) {
    return "stream_errors.provider_unavailable";
  }

  if (
    lower.includes("request timed out") ||
    lower.includes("timed out or interrupted") ||
    lower.includes("connection error") ||
    compact.includes("apitimeouterror") ||
    compact.includes("apiconnectionerror")
  ) {
    return "stream_errors.timeout_network";
  }

  if (lower.includes("model call failed after")) {
    return "stream_errors.model_call_failed";
  }

  return null;
}

/**
 * True only when the message reads like a bare error envelope.
 *
 * `classifyChatStreamError` keyword-matches raw upstream error strings, but
 * `finalizeStreamingMessages` feeds it arbitrary assistant answers: a long
 * troubleshooting reply that merely quotes error keywords ("401",
 * "insufficient_quota", "欠费", …) must not be flipped into an error bubble
 * (its original text gets replaced by the localized guidance). Real error
 * envelopes are short and unadorned; conversational answers that quote them
 * are not — guard on shape first, then classify.
 */
export function isChatStreamError(message: string | null | undefined): boolean {
  if (typeof message !== "string") return false;
  const text = message.trim();
  // Error envelopes (raw upstream error strings and localized
  // `stream_errors.*` sentences) are short.
  if (!text || text.length > 600) return false;
  // Markdown structure means a composed answer, not an error string.
  if (
    text.includes("```") ||
    text.includes("**") ||
    text.includes("`") ||
    text.includes("\n#") ||
    text.includes("\n|")
  ) {
    return false;
  }
  // Free-form CJK prose counts as an error only when it starts like one of
  // the localized error sentences ("模型服务…", "⚠ …", "agent error:" …).
  if (
    /[\u4e00-\u9fff]/.test(text) &&
    !/^(模型|对话|智能体|连接|⚠|agent error:|error:)/i.test(text)
  ) {
    return false;
  }
  return classifyChatStreamError(text) !== null;
}

/** Localized guidance for known failures; otherwise the original text. */
export function formatChatStreamError(
  message: string | null | undefined,
  t: TFunction,
): string {
  if (!message) return "";
  const key = classifyChatStreamError(message);
  if (!key) return message;
  return t(key, { defaultValue: message });
}

/** Optional settings deep-link for known stream failures. */
export function chatStreamErrorAction(
  message: string | null | undefined,
): StreamErrorAction | null {
  const key = classifyChatStreamError(message);
  if (!key) return null;
  return STREAM_ERROR_ACTIONS[key] ?? null;
}
