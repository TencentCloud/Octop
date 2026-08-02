import { describe, expect, it } from "vitest";
import {
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
