import { describe, expect, it } from "vitest";
import { convertHistoryMessages, mergeHistoryBehindLive } from "./useChat";
import type { ChatMessage } from "./sseHelpers";

function msg(
  id: string,
  role: "user" | "assistant",
  content: string,
): ChatMessage {
  return { id, role, content, status: "done", timestamp: 1 };
}

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

  it("maps inbound_attachments from the history API into gallery attachments", () => {
    const messages = convertHistoryMessages(
      [
        {
          role: "user",
          content: [{ type: "text", text: "这图是啥" }],
          id: "u1",
          inbound_attachments: [
            {
              filename: "1787277960_baidu_map.png",
              media_type: "image/png",
              kind: "image",
              workspace_path: "inbound/1787277960_baidu_map.png",
            },
          ],
        },
      ],
      "agent_1",
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]?.content).toBe("这图是啥");
    expect(messages[0]?.attachments?.[0]).toMatchObject({
      workspacePath: "inbound/1787277960_baidu_map.png",
      kind: "image",
    });
    expect(messages[0]?.attachments?.[0]?.url).toContain(
      "/api/agents/agent_1/",
    );
  });
});

describe("mergeHistoryBehindLive", () => {
  it("places older server history in front of a live inbound tail", () => {
    const history = [msg("h1", "user", "昨天"), msg("h2", "assistant", "好的")];
    const live = [msg("l1", "user", "你好")];
    expect(mergeHistoryBehindLive(history, live).map((m) => m.id)).toEqual([
      "h1",
      "h2",
      "l1",
    ]);
  });

  it("does not duplicate a user line already on the live tail", () => {
    const history = [msg("h1", "user", "昨天"), msg("h2", "user", "你好")];
    const live = [msg("l1", "user", "你好"), msg("l2", "assistant", "在")];
    expect(mergeHistoryBehindLive(history, live).map((m) => m.content)).toEqual([
      "昨天",
      "你好",
      "在",
    ]);
  });
});
