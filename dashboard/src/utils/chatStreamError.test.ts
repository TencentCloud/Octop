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

  it("leaves unknown messages alone", () => {
    expect(classifyChatStreamError("hello world")).toBeNull();
    expect(formatChatStreamError("hello world", t)).toBe("hello world");
  });

  it("formats known failures through i18n", () => {
    const msg =
      "No streaming chunk received for 30.0s (model=x, chunks_received=1)";
    expect(formatChatStreamError(msg, t)).toBe(
      "translated:stream_errors.stream_stall",
    );
  });
});

const troubleshootingAnswer = [
  "# 故障分析报告",
  "",
  "**背景**：服务端 finish_reason=stop、error audit 0 条。",
  "报错文案只是 keyword 分类：正文含 `401` / `invalid_api_key` 会显示 auth 文案，",
  "含 `402` / `insufficient_quota` / `欠费` / `余额不足` / `账户余额` 会显示额度文案。",
  "| 现象 | 真相 |",
  "|---|---|",
  "| 发 continue 就能续跑 | 下一条回答不含 keyword 就不误判 |",
  "",
  "**结论**：这是 content 扫描的 false positive。",
].join("\n");

// Regression tests for #1074: normal answers that merely mention error
// keywords must not be flipped into error bubbles by the content sniffer.
describe("isChatStreamError false-positive guard (#1074)", () => {
  it("does not flip a long troubleshooting answer that quotes error keywords", () => {
    expect(isChatStreamError(troubleshootingAnswer)).toBe(false);
  });

  it("does not flag markdown-formatted replies", () => {
    expect(isChatStreamError("**表格** 里提到 `insufficient_quota` 和欠费")).toBe(
      false,
    );
  });

  it("does not flag free-form CJK prose that merely mentions a keyword", () => {
    expect(isChatStreamError("欠费问题已经排查过了，不是这个原因")).toBe(false);
    expect(
      isChatStreamError("401 invalid_api_key 之类的问题都修好了，见下文分析"),
    ).toBe(false);
  });

  it("does not flag over-long content", () => {
    expect(isChatStreamError(`${"a".repeat(601)} 余额不足`)).toBe(false);
  });

  it("leaves quoted keywords in short echo replies alone", () => {
    expect(
      isChatStreamError('"账户余额欠费，insufficient_quota，error code: 402"'),
    ).toBe(false);
  });

  it("leaves localized i18n sentences delivered as content alone", () => {
    expect(
      isChatStreamError(
        "模型服务返回余额或额度不足。请为该 API Key 对应的账户充值或升级套餐后再试。",
      ),
    ).toBe(false);
  });

  it("still classifies raw upstream error strings", () => {
    expect(
      isChatStreamError(
        "Error code: 402 - {'error': {'message': 'insufficient_quota'}}",
      ),
    ).toBe(true);
    expect(isChatStreamError("error: connection error while posting")).toBe(
      true,
    );
    expect(isChatStreamError("no streaming chunk received")).toBe(true);
  });
});
