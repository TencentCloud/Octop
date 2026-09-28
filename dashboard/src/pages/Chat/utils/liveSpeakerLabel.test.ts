import { describe, expect, it } from "vitest";
import {
  hasInFlightTool,
  hasStreamingThinking,
  resolveLiveSpeakerNames,
} from "./liveSpeakerLabel";

describe("resolveLiveSpeakerNames", () => {
  const agents = [
    { agent_id: "host", name: "主持" },
    { agent_id: "doctor", name: "临床助手" },
    { agent_id: "nurse", name: "护理助手" },
  ];

  it("maps member ids to display names", () => {
    expect(
      resolveLiveSpeakerNames(["doctor", "nurse"], agents, {
        hostId: "host",
        hostName: "主持",
      }),
    ).toEqual(["临床助手", "护理助手"]);
  });

  it("treats empty and host id as the host", () => {
    expect(
      resolveLiveSpeakerNames(["", "host"], agents, {
        hostId: "host",
        hostName: "团队主持",
      }),
    ).toEqual(["团队主持"]);
  });

  it("falls back to the raw id when the agent is unknown", () => {
    expect(resolveLiveSpeakerNames(["mystery"], agents)).toEqual(["mystery"]);
  });

  it("caps the list", () => {
    expect(
      resolveLiveSpeakerNames(["doctor", "nurse", "mystery"], agents, {
        limit: 2,
      }),
    ).toEqual(["临床助手", "护理助手"]);
  });
});

describe("hasInFlightTool", () => {
  it("detects a streaming tool without output", () => {
    expect(
      hasInFlightTool([
        { status: "streaming", toolData: { name: "read_file" } },
      ]),
    ).toBe(true);
  });

  it("ignores completed tools", () => {
    expect(
      hasInFlightTool([
        {
          status: "done",
          toolData: { name: "read_file", output: "ok" },
        },
      ]),
    ).toBe(false);
  });
});

describe("hasStreamingThinking", () => {
  it("detects streaming reasoning bubbles", () => {
    expect(
      hasStreamingThinking([{ status: "streaming", type: "reasoning" }]),
    ).toBe(true);
  });

  it("detects thinking content blocks", () => {
    expect(
      hasStreamingThinking([
        {
          status: "streaming",
          contentBlocks: [{ type: "thinking" }],
        },
      ]),
    ).toBe(true);
  });
});
