import { describe, expect, it } from "vitest";
import {
  chatStreamErrorAction,
  classifyChatStreamError,
  formatChatStreamError,
  isChatStreamError,
} from "./chatStreamError";

const t = ((key: string) => `translated:${key}`) as unknown as (
  key: string,
  opts?: { defaultValue?: string },
) => string;

describe("classifyChatStreamError", () => {
  it("classifies StreamChunkTimeoutError retry text as stream_stall", () => {
    const msg =
      "Model call failed after 3 attempts with StreamChunkTimeoutError: " +
      "No streaming chunk received for 120.0s (model=MiniMax-M2.7, chunks_received=122).";
    expect(classifyChatStreamError(msg)).toBe("stream_errors.stream_stall");
    expect(isChatStreamError(msg)).toBe(true);
  });

  it("classifies rate limit and auth errors", () => {
    expect(
      classifyChatStreamError("Error code: 429 - rate_limit_exceeded"),
    ).toBe("stream_errors.rate_limit");
    expect(
      classifyChatStreamError("Error code: 401 - Incorrect API key provided"),
    ).toBe("stream_errors.auth");
  });

  it("classifies insufficient balance / 402", () => {
    const msg =
      "Error code: 402 - {'error': {'message': 'Insufficient Balance', " +
      "'type': 'unknown_error', 'param': None, 'code': 'invalid_request_error'}}";
    expect(classifyChatStreamError(msg)).toBe(
      "stream_errors.insufficient_balance",
    );
    expect(
      classifyChatStreamError(
        "HTTP 402 POST https://api.example.com/v1/chat: Insufficient Balance",
      ),
    ).toBe("stream_errors.insufficient_balance");
    expect(chatStreamErrorAction(msg)).toEqual({
      path: "/admin/models",
      labelKey: "modelConfig.configureButton",
    });
  });

  it("classifies MindIE 422 parameter rejection as invalid_request", () => {
    const msg =
      "Error code: 422 - {error:'Check open ai req parameter error'," +
      "'error_type': 'Input Validation Error'}";
    expect(classifyChatStreamError(msg)).toBe("stream_errors.invalid_request");
    expect(chatStreamErrorAction(msg)).toEqual({
      path: "/admin/models",
      labelKey: "chat.disableStreamUsageAndRetry",
      fix: "disable_stream_usage",
    });
  });

  it("classifies HTTP 5xx as provider_unavailable", () => {
    expect(classifyChatStreamError("HTTP 503: service overloaded")).toBe(
      "stream_errors.provider_unavailable",
    );
  });

  it("classifies LangGraph recursion limit as recursion_limit", () => {
    const msg =
      "Recursion limit of 2 reached without hitting a stop condition. " +
      "You can increase the limit by setting the `recursion_limit` config key.\n" +
      "For troubleshooting, visit: " +
      "https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT";
    expect(classifyChatStreamError(msg)).toBe("stream_errors.recursion_limit");
    expect(
      classifyChatStreamError("GraphRecursionError: GRAPH_RECURSION_LIMIT"),
    ).toBe("stream_errors.recursion_limit");
    expect(chatStreamErrorAction(msg)).toEqual({
      path: "/agent-config",
      labelKey: "chat.goToAgentConfig",
    });
  });

  it("classifies leftover Windows outside-root paths", () => {
    const msg =
      String.raw`ValueError: Path:D:\octop-data\data\文章存稿\x.md ` +
      String.raw`outside root directory: C:\Users\Administrator`;
    expect(classifyChatStreamError(msg)).toBe(
      "stream_errors.path_outside_root",
    );
    expect(chatStreamErrorAction(msg)).toEqual({
      path: "/agent-config",
      labelKey: "chat.goToAgentConfig",
    });
  });

  it("leaves unknown messages alone", () => {
    expect(classifyChatStreamError("hello world")).toBeNull();
    expect(formatChatStreamError("hello world", t)).toBe("hello world");
  });

  it("keeps the concrete cause for retry-exhausted unknown errors", () => {
    const msg = "Model call failed after 3 attempts with RuntimeError: boom";
    expect(classifyChatStreamError(msg)).toBe(
      "stream_errors.model_call_failed",
    );
    expect(formatChatStreamError(msg, t)).toBe(
      "translated:stream_errors.model_call_failed_detail",
    );
  });

  it("classifies a model-retry recovery prompt by its technical detail", () => {
    const msg =
      "[model_call_failed]\nThe model API request failed.\n\n" +
      "Technical detail: Error code: 400 - This model's maximum context length is 128000 tokens";
    expect(classifyChatStreamError(msg)).toBe("stream_errors.context_length");
  });

  it("formats known failures through i18n", () => {
    const msg =
      "No streaming chunk received for 30.0s (model=x, chunks_received=1)";
    expect(formatChatStreamError(msg, t)).toBe(
      "translated:stream_errors.stream_stall",
    );
  });

  it("does not treat ordinary answers that mention errors as stream failures", () => {
    expect(
      isChatStreamError(
        "If you see Error code: 429 or rate_limit, wait and retry.",
      ),
    ).toBe(false);
    expect(isChatStreamError("Check HTTP 401 if the API key is wrong.")).toBe(
      false,
    );
    expect(isChatStreamError("The request timed out; we can try again.")).toBe(
      false,
    );
    expect(
      classifyChatStreamError(
        "If you see Error code: 429 or rate_limit, wait and retry.",
      ),
    ).toBe("stream_errors.rate_limit");
  });
});
