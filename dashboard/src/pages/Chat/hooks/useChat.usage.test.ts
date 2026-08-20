import { describe, expect, it } from "vitest";
import { convertHistoryMessages } from "./useChat";

describe("history token usage", () => {
  it("normalizes provider cache details and rolls up every model call", () => {
    const messages = convertHistoryMessages([
      { role: "user", content: "hello", id: "u1" },
      {
        role: "assistant",
        content: "working",
        id: "a1",
        usage: {
          input_tokens: 100,
          output_tokens: 5,
          input_token_details: { cache_read: 70 },
        },
      },
      {
        role: "assistant",
        content: "done",
        id: "a2",
        usage: {
          input_tokens: 120,
          output_tokens: 6,
          input_token_details: { cache_read: 90 },
          output_token_details: { reasoning: 2 },
        },
      },
    ]);

    expect(messages[1]?.usage).toBeUndefined();
    expect(messages[2]?.usage).toMatchObject({
      input_tokens: 220,
      uncached_input_tokens: 60,
      cache_read_tokens: 160,
      cache_write_tokens: 0,
      output_tokens: 11,
      reasoning_tokens: 2,
      total_tokens: 231,
      model_calls: 2,
      last_input_tokens: 120,
    });
  });
});
