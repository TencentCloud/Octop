import { describe, expect, it } from "vitest";
import { parseHarnessChunk } from "./parseHarnessChunk";

describe("parseHarnessChunk usage", () => {
  it("keeps the stable call id and cache-aware usage fields", () => {
    const chunk = parseHarnessChunk(
      'data: {"type":"usage","call_id":"call-1","model":"deepseek-v4","usage":{"input_tokens":100,"uncached_input_tokens":30,"cache_read_tokens":70,"cache_write_tokens":0,"output_tokens":9,"reasoning_tokens":4,"total_tokens":109}}',
    );

    expect(chunk).toEqual({
      type: "usage",
      call_id: "call-1",
      model: "deepseek-v4",
      node: undefined,
      usage: {
        input_tokens: 100,
        uncached_input_tokens: 30,
        cache_read_tokens: 70,
        cache_write_tokens: 0,
        output_tokens: 9,
        reasoning_tokens: 4,
        total_tokens: 109,
      },
    });
  });

  it("parses authoritative task plan updates", () => {
    const chunk = parseHarnessChunk(
      'data: {"type":"task_plan_updated","thread_id":"thread-1","task_state":{"thread_id":"thread-1","available":true,"status":"active","items":[{"id":"1","content":"Ship","status":"in_progress"}],"completed":0,"total":1}}',
    );

    expect(chunk).toMatchObject({
      type: "task_plan_updated",
      thread_id: "thread-1",
      task_state: {
        status: "active",
        total: 1,
      },
    });
  });
});
