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
  "stream_errors.invalid_request",
  "stream_errors.model_call_failed",
  "stream_errors.path_outside_root",
] as const;

export type StreamErrorKey = (typeof _STREAM_ERROR_KEYS)[number];

export type StreamErrorAction = {
  path: string;
  labelKey: string;
  /** One-click fix the chat bubble can run instead of only navigating. */
  fix?: "disable_stream_usage";
};

const MODEL_RETRY_FAILURE_MARK = "[model_call_failed]";
const RETRY_WRAPPER_RE = /^model call failed after \d+ attempts?\s+with\s+/i;
const TECHNICAL_DETAIL_RE = /technical detail:\s*([\s\S]+)$/i;

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
    "stream_errors.invalid_request": {
      path: "/admin/models",
      labelKey: "chat.disableStreamUsageAndRetry",
      fix: "disable_stream_usage",
    },
    "stream_errors.recursion_limit": {
      path: "/agent-config",
      labelKey: "chat.goToAgentConfig",
    },
    "stream_errors.path_outside_root": {
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

function unwrapModelRetryMessage(message: string): string {
  let msg = normalizeMessage(message)
    .replaceAll(MODEL_RETRY_FAILURE_MARK, " ")
    .trim();
  const tech = msg.match(TECHNICAL_DETAIL_RE);
  if (tech?.[1]) return tech[1].trim();
  msg = msg.replace(RETRY_WRAPPER_RE, "").trim();
  return msg || normalizeMessage(message);
}

/** Return a stable i18n key for known model/stream failures, else null. */
export function classifyChatStreamError(
  message: string | null | undefined,
): StreamErrorKey | null {
  if (!message) return null;
  const raw = normalizeMessage(message);
  const msg = unwrapModelRetryMessage(message);
  if (!msg && !raw) return null;
  const lower = msg.toLowerCase();
  const compact = lower.replace(/[_\s]/g, "");

  if (
    lower.includes("outside root directory") ||
    lower.includes("path traversal not allowed")
  ) {
    return "stream_errors.path_outside_root";
  }

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
    lower.includes("error code: 422") ||
    lower.includes("http 422") ||
    lower.includes("check open ai req parameter") ||
    lower.includes("input validation error")
  ) {
    return "stream_errors.invalid_request";
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

  if (
    raw.toLowerCase().includes("model call failed after") ||
    raw.includes(MODEL_RETRY_FAILURE_MARK)
  ) {
    return "stream_errors.model_call_failed";
  }

  return null;
}

function isModelRetryEnvelope(message: string | null | undefined): boolean {
  if (!message) return false;
  const raw = normalizeMessage(message);
  return (
    raw.toLowerCase().includes("model call failed after") ||
    raw.includes(MODEL_RETRY_FAILURE_MARK)
  );
}

/** True only for ModelRetryMiddleware envelopes, not ordinary answers. */
export function isChatStreamError(message: string | null | undefined): boolean {
  return isModelRetryEnvelope(message);
}

/** Localized guidance for known failures; otherwise the original text. */
export function formatChatStreamError(
  message: string | null | undefined,
  t: TFunction,
): string {
  if (!message) return "";
  const key = classifyChatStreamError(message);
  const detail = unwrapModelRetryMessage(message);
  if (key && key !== "stream_errors.model_call_failed") {
    return t(key, { defaultValue: message });
  }
  if (detail && detail !== normalizeMessage(message)) {
    return t("stream_errors.model_call_failed_detail", {
      detail,
      defaultValue: detail,
    });
  }
  if (key) return t(key, { defaultValue: message });
  return message;
}

/** Optional settings deep-link for known stream failures. */
export function chatStreamErrorAction(
  message: string | null | undefined,
): StreamErrorAction | null {
  const key = classifyChatStreamError(message);
  if (!key) return null;
  return STREAM_ERROR_ACTIONS[key] ?? null;
}
