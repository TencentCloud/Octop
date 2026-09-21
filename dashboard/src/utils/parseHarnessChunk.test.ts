import { describe, expect, it } from "vitest";
import { parseHarnessChunk, streamSpeakerId } from "./parseHarnessChunk";

describe("parseHarnessChunk token", () => {
  it("keeps a team-room speaker id on fanned-in tokens", () => {
    const chunk = parseHarnessChunk(
      'data: {"type":"token","content":"rest","agent_id":"doctor"}',
    );
    expect(chunk).toMatchObject({
      type: "token",
      content: "rest",
      agent_id: "doctor",
    });
  });
});

describe("parseHarnessChunk team speaker", () => {
  it("keeps a speaker id on reasoning, tools, and done", () => {
    expect(
      parseHarnessChunk(
        'data: {"type":"reasoning","content":"think","agent_id":"doctor"}',
      ),
    ).toMatchObject({ type: "reasoning", agent_id: "doctor" });
    expect(
      parseHarnessChunk(
        'data: {"type":"tool_call_chunk","id":"c1","name":"read","agent_id":"doctor"}',
      ),
    ).toMatchObject({ type: "tool_call_chunk", agent_id: "doctor" });
    expect(
      parseHarnessChunk('data: {"type":"done","agent_id":"doctor"}'),
    ).toEqual({ type: "done", agent_id: "doctor", team_wrapup: false });
  });

  it("accepts the agent alias and ignores the graph node name", () => {
    expect(
      parseHarnessChunk(
        'data: {"type":"token","content":"hi","agent":"doctor"}',
      ),
    ).toMatchObject({ type: "token", content: "hi", agent_id: "doctor" });
    expect(streamSpeakerId({ type: "token", agent: "doctor" })).toBe("doctor");
    expect(streamSpeakerId({ type: "token", node: "agent" })).toBeUndefined();
    expect(streamSpeakerId({ type: "token", agent: "agent" })).toBeUndefined();
    expect(
      streamSpeakerId({ type: "token", agent: "agent", agent_id: "host" }),
    ).toBe("host");
  });
});

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
});
