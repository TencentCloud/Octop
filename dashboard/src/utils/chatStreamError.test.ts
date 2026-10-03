import { describe, expect, it } from "vitest";
import {
  chatStreamErrorAction,
  classifyChatStreamError,
  formatChatStreamError,
  isBareErrorEnvelope,
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
});

describe("isChatStreamError only flags bare error envelopes (#1074)", () => {
  // A real answer that quotes a provider error while explaining it. The classifier
  // still finds the substring, but the message body must stay readable.
  const troubleshootingAnswer = [
    "## 结论：不是服务坏了，是健康检查探针指错了路径",
    "",
    "```",
    "wget: server returned error: HTTP/1.1 401 Unauthorized",
    "```",
    "",
    "| 路径 | 结果 |",
    "| --- | --- |",
    "| `/` | 401 ← 探针打的就是这个 |",
    "| `/api/system/version` | 200 |",
  ].join("\n");

  it("still classifies the quoted error string itself", () => {
    expect(classifyChatStreamError(troubleshootingAnswer)).toBe(
      "stream_errors.auth",
    );
  });

  it("does not treat a formatted answer as a stream failure", () => {
    expect(isChatStreamError(troubleshootingAnswer)).toBe(false);
  });

  it("does not treat long unformatted prose as a stream failure", () => {
    const long = `排查记录：${"服务端返回 401 Unauthorized，请检查 API key 是否过期。".repeat(40)}`;
    expect(long.length).toBeGreaterThan(600);
    expect(classifyChatStreamError(long)).toBe("stream_errors.auth");
    expect(isChatStreamError(long)).toBe(false);
  });

  it("keeps flagging bare error envelopes", () => {
    expect(
      isChatStreamError("Error code: 401 - {'code': 'invalid_api_key'}"),
    ).toBe(true);
    expect(
      isChatStreamError("HTTP 503: upstream service temporarily unavailable"),
    ).toBe(true);
  });

  it("rejects empty input as an envelope", () => {
    expect(isBareErrorEnvelope("")).toBe(false);
    expect(isBareErrorEnvelope("   ")).toBe(false);
    expect(isBareErrorEnvelope(null)).toBe(false);
    expect(isBareErrorEnvelope(undefined)).toBe(false);
    expect(isBareErrorEnvelope("Error code: 401 - invalid_api_key")).toBe(true);
  });
});
