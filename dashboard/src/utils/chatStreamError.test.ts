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

  it("classifies exhausted accounts as insufficient balance even on 429 / 403", () => {
    const exhausted = [
      // OpenAI, surfaced by the model retry middleware
      "Model call failed after 3 attempts with RateLimitError: Error code: 429 - " +
        "{'error': {'message': 'You exceeded your current quota, please check your plan " +
        "and billing details. For more information on this error, read the docs: " +
        "https://platform.openai.com/docs/guides/error-codes/api-errors.', " +
        "'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}",
      // Zhipu 1113
      "Error code: 429 - {'error': {'code': '1113', 'message': '您的账户已欠费，请充值后重试'}}",
      // Moonshot / Kimi
      "Error code: 429 - {'error': {'message': 'Your account org-abc<ak-xyz> is suspended " +
        "due to insufficient balance, please recharge your account', " +
        "'type': 'exceeded_current_quota_error'}}",
      // Anthropic
      "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', " +
        "'message': 'Your credit balance is too low to access the Anthropic API. " +
        "Please go to Plans & Billing to upgrade or purchase credits.'}}",
      // SiliconFlow
      "Error code: 403 - {'code': 30001, 'message': 'Sorry, your account balance is " +
        "insufficient', 'data': None}",
      // Volcengine Ark
      "Error code: 403 - {'error': {'code': 'AccountOverdueError', 'message': 'The request " +
        "failed because your account has an overdue balance.', 'type': 'Forbidden'}}",
    ];
    for (const msg of exhausted) {
      expect(classifyChatStreamError(msg)).toBe(
        "stream_errors.insufficient_balance",
      );
    }
  });

  it("keeps throttling that reuses quota wording as a rate limit", () => {
    const throttled = [
      // DashScope compatible mode: Throttling.AllocationQuota
      "Error code: 429 - {'error': {'code': 'insufficient_quota', " +
        "'message': 'Allocated quota exceeded, please increase your quota limit.'}}",
      // DashScope compatible mode: TPM limit with OpenAI's quota text
      "Error code: 429 - {'error': {'message': 'You exceeded your current quota, please " +
        "check your plan and billing details. For details, see: " +
        "https://help.aliyun.com/zh/model-studio/error-code#token-limit', " +
        "'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}",
      // OpenAI TPM limit
      "Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-4o in " +
        "organization org-abc on tokens per min (TPM): Limit 30000, Used 29854, " +
        "Requested 1200.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
      // Zhipu 1302
      "Error code: 429 - {'error': {'code': '1302', 'message': '您的账户已达到速率限制，请您控制请求频率'}}",
    ];
    for (const msg of throttled) {
      expect(classifyChatStreamError(msg)).toBe("stream_errors.rate_limit");
    }
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
