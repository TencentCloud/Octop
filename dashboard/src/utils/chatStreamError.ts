/** Classify and localize chat / model stream failures for user-facing UI. */

import type { TFunction } from "i18next";

const STREAM_ERROR_KEYS = [
  "stream_errors.stream_stall",
  "stream_errors.rate_limit",
  "stream_errors.auth",
  "stream_errors.context_length",
  "stream_errors.recursion_limit",
  "stream_errors.timeout_network",
  "stream_errors.provider_unavailable",
  "stream_errors.model_call_failed",
] as const;

export type StreamErrorKey = (typeof STREAM_ERROR_KEYS)[number];

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
    lower.includes("rate_limit") ||
    compact.includes("ratelimiterror") ||
    lower.includes("too many requests")
  ) {
    return "stream_errors.rate_limit";
  }

  if (
    lower.includes("error code: 401") ||
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
    lower.includes("error code: 503")
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

export function isChatStreamError(message: string | null | undefined): boolean {
  return classifyChatStreamError(message) !== null;
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
